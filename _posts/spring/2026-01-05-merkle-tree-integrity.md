---
title: "Merkle Tree로 양도 이력 무결성 검증하기"
date: 2026-01-05 12:00:00 +0900
categories: [Spring]
tags: [spring, merkle-tree, blockchain, integrity, security]
---

## 개요

티켓 양도 기능에서 **감사/CS 대응용 히스토리**가 필요했다. 금전적 가치가 있고 사후 분쟁 가능성이 높은 기능이기 때문에, 단순히 DB에 기록하는 것만으로는 **내부 조작 위험**이 있다.

블록체인의 핵심 원리인 **Merkle Tree**를 적용하여, DB 조작이 발생하더라도 **위변조를 감지**할 수 있는 구조를 구현했다.

---

## 1. 설계 목표

- 실시간 안정성
- 위변조 방지 (완전 방지는 X)
- **위변조 감지**
- 사후 검증 가능
- 운영 부담 최소화 (이미 인프라 구축되어 있는 Grafana/Loki 활용)

---

## 2. Merkle Tree란?

여러 기록을 **하나의 지문(hash)로 압축**하는 기술이다.

### 문제 상황

```java
- 양도 기록 A
- 양도 기록 B
- 양도 기록 C
```

→ TicketTransferHistory 엔티티에 일반적인 구현처럼 JPA 사용해서 저장할 시
→ **DB 조작하면 알 수가 없음**

### Merkle Tree 동작 방식

**1. 각 기록을 해시**

```
H(A)   H(B)   H(C)
```

**2. 둘씩 묶어서 다시 해시**

```
H(H(A) + H(B))   H(H(C) + H(C))
```

**3. 최종 루트(root) 하나로 모일 때까지**

```
MERKLE_ROOT = H( left + right )
```

이 root 하나가 전체 양도 이력의 지문이 된다.
→ **기록 하나라도 바뀌면 최종 root가 달라짐**

---

## 3. 외부 앵커(Anchor)

### 문제

Merkle tree 방식을 적용한다 한들, **운영자가 DB랑 root를 같이 맞춰서 바꾸면 끝**이다.

### 해결

**root를 서버 밖에 남긴다** → 이걸 **Anchor(앵커)**라고 한다.

### 외부 앵커의 조건

- 서버 외부일 것 → DB 조작과 분리하기 위함
- 시간 기록 → 언제 상태인지 알 수 있게
- 변경 흔적 → 수정 시에 추적할 수 있도록

### 우리 프로젝트의 앵커

**Alloy → Loki → Grafana 로그 파이프라인**

- 로그는 append-only
- 과거 로그 수정 사실상 불가
- 이미 구축되어 있는 인프라 활용

---

## 4. 전체 구조

```
Ticket Transfer(양도) 발생
→ TicketTransferHistory 저장
→ 각 이력에 대한 SHA-256 해시 생성 (Leaf 노드)
→ Merkle Tree 구성 → Merkle Root 계산
→ Merkle Root + 메타정보를 Alloy > Grafana Cloud Loki 파이프라인을 통해 외부 시스템에 앵커링
→ 사후 검증 시 DB 이력으로 Merkle Root 재계산
→ Loki 로그에 기록된 Root와 비교
→ 일치: 정상 / 불일치: 위변조 감지
```

---

## 5. 핵심 구현

### 5-1. TicketTransferHistory

양도 발생 1건 → Merkle Tree의 Leaf

```java
+ ticketId (어떤 티켓)
+ fromUserId (이전 소유자)
+ toUserId (새로운 소유자)
+ transferredAt (순서성과 시간 증명)
```

**해시 생성 로직:**

```java
public String computeHash() {
    String data = String.join(":",
        String.valueOf(ticketId),
        String.valueOf(fromUserId),
        String.valueOf(toUserId),
        transferredAt.format(DateTimeFormatter.ISO_LOCAL_DATE_TIME)
    );

    try {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hashBytes = digest.digest(data.getBytes(StandardCharsets.UTF_8));
        return bytesToHex(hashBytes);
    } catch (NoSuchAlgorithmException e) {
        throw new RuntimeException("SHA-256 algorithm not available", e);
    }
}
```

- SHA-256 사용
- 동일 데이터는 항상 동일한 해시로 변환
- **필드 중 하나라도 바뀌면 해시 완전히 변경**

### 5-2. MerkleUtil

여러 이력 → 하나의 root 해시값으로 압축 수행

```java
public static final int MAX_LEAVES = 10_000;
private static final int MAX_ITERATIONS = 20;

public static String buildRoot(List<String> hashes) {
    if (hashes == null || hashes.isEmpty()) {
        return "";
    }

    if (hashes.size() == 1) {
        return hashes.get(0);
    }

    if (hashes.size() > MAX_LEAVES) {
        throw new ErrorException(CommonErrorCode.MERKLE_TOO_MANY_LEAVES);
    }

    List<String> currentLevel = new ArrayList<>(hashes);
    int iterations = 0;

    while (currentLevel.size() > 1) {
        if (++iterations > MAX_ITERATIONS) {
            throw new ErrorException(CommonErrorCode.MERKLE_BUILD_FAILED);
        }
        currentLevel = buildNextLevel(currentLevel);
    }

    return currentLevel.get(0);
}
```

- Leaf 하나라도 변경 → Root가 달라짐
- 전체 데이터를 보지 않아도 무결성 검증 가능
- 블록체인에서 가장 핵심적으로 쓰이는 구조

### 5-3. TicketService - 양도 처리 및 앵커링

```java
@Transactional
public void transferTicket(Long ticketId, Long userId, String targetNickname) {
    // 비관락으로 조회
    Ticket ticket = ticketRepository.findByIdForUpdate(ticketId);

    // ... 검증 로직 ...

    // 양도 처리
    ticket.transferTo(target);

    // 양도 이력 저장
    TicketTransferHistory history = TicketTransferHistory.record(ticketId, fromUserId, target.getId());
    transferHistoryRepository.save(history);

    // Merkle Root 앵커링 (Loki로 전송됨)
    anchorTransferHistory(ticketId, history);

    log.debug("[Ticket Transfer] ticketId={}, from={}, to={}", ticketId, fromUserId, target.getId());
}

private void anchorTransferHistory(Long ticketId, TicketTransferHistory latestHistory) {
    List<TicketTransferHistory> histories =
        transferHistoryRepository.findByTicketIdOrderByTransferredAtDesc(ticketId);

    List<String> hashes = histories.stream()
        .map(TicketTransferHistory::computeHash)
        .toList();

    String merkleRoot = MerkleUtil.buildRoot(hashes);

    // 구조화된 로그 - Loki에서 파싱 가능 (외부 앵커)
    log.info("[MERKLE_ANCHOR] ticketId={}, root={}, count={}, latestHash={}",
        ticketId,
        merkleRoot,
        histories.size(),
        latestHistory.computeHash()
    );
}
```

**최종적으로 anchorTransferHistory에서 나가는 로그:**
- DB 밖으로 나감
- Loki는 append-only 로그
- Grafana Cloud에 저장됨

> **DB를 조작해도 로그는 사라지지 않음**

### 5-4. MerkleAnchorService - 수동 검증 서비스

운영/CS/장애 대응용으로, 특정 티켓의 양도 이력이 조작되었는지 확인한다.

```java
// 특정 티켓의 현재 Merkle Root 계산
@Transactional(readOnly = true)
public String computeTicketMerkleRoot(Long ticketId) {
    List<TicketTransferHistory> histories =
        transferHistoryRepository.findByTicketIdOrderByTransferredAtDesc(ticketId);

    if (histories.isEmpty()) {
        return "";
    }

    List<String> hashes = histories.stream()
        .map(TicketTransferHistory::computeHash)
        .toList();

    return MerkleUtil.buildRoot(hashes);
}

/**
 * 특정 티켓의 Merkle Root 검증
 * Loki에 기록된 expectedRoot와 현재 DB 상태 비교
 */
@Transactional(readOnly = true)
public boolean verifyTicketHistory(Long ticketId, String expectedRoot) {
    String currentRoot = computeTicketMerkleRoot(ticketId);

    boolean isValid = currentRoot.equals(expectedRoot);

    if (!isValid) {
        log.warn("[MERKLE_VERIFY_FAILED] ticketId={}, expected={}, actual={}",
            ticketId, expectedRoot, currentRoot);
    } else {
        log.info("[MERKLE_VERIFY_SUCCESS] ticketId={}, root={}", ticketId, currentRoot);
    }

    return isValid;
}
```

**검증 방법:**
1. DB에 있는 현재 양도 이력 기준 재계산
2. Loki에서 확인한 expectedRoot와 비교
3. 같으면 정상 / 다르면 **위변조 발생 탐지**

---

## 6. 검증 흐름 요약

| 단계 | 설명 |
|------|------|
| 1. 양도 발생 | TicketTransferHistory 저장 |
| 2. 해시 생성 | SHA-256으로 각 이력 해시 |
| 3. Merkle Root 계산 | 트리 구조로 압축 |
| 4. 외부 앵커링 | Loki에 로그로 전송 |
| 5. 검증 시 | DB 재계산 vs Loki 로그 비교 |

---

## 정리

1. **Merkle Tree**는 여러 기록을 하나의 해시로 압축하는 기술
2. **기록 하나라도 변경되면 root가 달라짐** → 위변조 감지 가능
3. DB만 있으면 내부 조작이 가능하므로 **외부 앵커(Loki)**가 필요
4. 이미 구축된 **로그 파이프라인(Alloy → Loki → Grafana)**을 활용
5. 완전한 위변조 방지는 아니지만, **사후 검증과 감사 대응**에 효과적

---

## 참고

- [[블록체인 뜻] 머클트리란? 생성과정, 구성요소, 장점](https://brunch.co.kr/@gapcha/263)
- [쉽게 설명하는 블록체인 : 머클트리(Merkle Trees)란](https://www.banksalad.com/contents/%EC%89%BD%EA%B2%8C-%EC%84%A4%EB%AA%85%ED%95%98%EB%8A%94-%EB%B8%94%EB%A1%9D%EC%B2%B4%EC%9D%B8-%EB%A8%B8%ED%81%B4%ED%8A%B8%EB%A6%AC-Merkle-Trees-%EB%9E%80-ilULl)
