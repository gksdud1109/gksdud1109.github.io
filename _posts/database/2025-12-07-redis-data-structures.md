---
title: "Redis 자료구조 - List, Set, Sorted Set, Hash, Bitmap 활용 가이드"
date: 2025-12-07 13:00:00 +0900
categories: [Database]
tags: [database, redis, data-structure, spring, redistemplate]
---

## 개요

Redis는 단순 문자열 외에도 **List, Set, Sorted Set, Hash, Bitmap** 등 다양한 자료구조를 제공한다. 각 자료구조의 특성을 이해하고 적절히 활용하면 복잡한 요구사항도 효율적으로 구현할 수 있다. 이 글에서는 각 자료구조의 개념, 주요 명령어, Spring RedisTemplate 사용 예시를 정리한다.

---

## 1. List

### 자료구조 설명

**List는 문자열 요소들의 연결 리스트(linked list) 형태로 구현된 순서가 있는 컬렉션**이다. 리스트의 양 끝에서 삽입/삭제는 매우 빠르며(O(1)), 인덱스로 접근하는 경우에는 리스트 길이에 비례하여 느려질 수 있다(O(N)).

**활용 예시:**
- 작업 대기열(큐) 구현
- 고정 길이 로그 관리 (LTRIM)
- 스택 구현

### 주요 명령어

| 명령어 | 설명 |
|--------|------|
| LPUSH/RPUSH | 리스트의 왼쪽/오른쪽에 요소 추가 |
| LPOP/RPOP | 리스트의 왼쪽/오른쪽에서 요소 제거 및 반환 |
| LRANGE | 지정한 범위의 요소들 반환 |
| LLEN | 리스트 길이 반환 |
| LTRIM | 지정한 범위만 남기고 삭제 |
| BLPOP/BRPOP | 블로킹 방식의 POP (생산자-소비자 패턴) |

### Redis CLI 예시

```bash
redis> RPUSH tasks "task1"  # [task1]
(integer) 1
redis> RPUSH tasks "task2"  # [task1 task2]
(integer) 2
redis> LRANGE tasks 0 -1
1) "task1"
2) "task2"
redis> LPOP tasks  # [task2]
"task1"
redis> LLEN tasks
(integer) 1
```

### Spring RedisTemplate 사용 예시

```java
@Autowired
private RedisTemplate<String, String> redisTemplate;

public void useListQueue() {
    ListOperations<String, String> listOps = redisTemplate.opsForList();
    // 오른쪽 끝에 작업 추가 (큐의 enqueue)
    listOps.rightPush("jobQueue", "job1");
    listOps.rightPush("jobQueue", "job2");
    // 왼쪽 끝에서 작업 가져오기 (큐의 dequeue)
    String nextJob = listOps.leftPop("jobQueue");
    System.out.println("Processing job: " + nextJob);
    // 현재 큐에 남은 모든 작업 확인
    List<String> allJobs = listOps.range("jobQueue", 0, -1);
    System.out.println("Pending jobs: " + allJobs);
}
```

---

## 2. Set

### 자료구조 설명

**Set은 순서가 없는(unordered) 문자열들의 집합**이며, **중복을 허용하지 않는(unique) 자료구조**이다. 동일한 값이 두 번 추가되면 한 번만 저장되므로 중복 제거가 자동으로 이루어진다.

**활용 예시:**
- 회원 ID 집합, 태그 모음
- 고유 방문자 IP 집합
- 공통 친구 찾기 (교집합 연산)

### 주요 명령어

| 명령어 | 설명 |
|--------|------|
| SADD | Set에 멤버 추가 (중복 무시) |
| SREM | Set에서 멤버 제거 |
| SISMEMBER | 멤버 존재 여부 확인 |
| SMEMBERS | 모든 멤버 반환 |
| SCARD | 멤버 수 반환 |
| SINTER | 여러 Set의 교집합 반환 |

### Redis CLI 예시

```bash
redis> SADD onlineUsers "user1"
(integer) 1
redis> SADD onlineUsers "user2" "user3"
(integer) 2
redis> SADD onlineUsers "user1"
(integer) 0                   # "user1"은 이미 존재하므로 추가되지 않음
redis> SMEMBERS onlineUsers
1) "user1"
2) "user2"
3) "user3"
redis> SISMEMBER onlineUsers "user2"
(integer) 1
redis> SCARD onlineUsers
(integer) 3
```

### Spring RedisTemplate 사용 예시

```java
public void useSetExample() {
    SetOperations<String, String> setOps = redisTemplate.opsForSet();
    // Set에 멤버 추가
    setOps.add("fruits", "apple");
    setOps.add("fruits", "banana");
    setOps.add("fruits", "apple");  // 중복 추가 (무시됨)
    // 모든 멤버 조회
    Set<String> all = setOps.members("fruits");
    System.out.println("과일 목록: " + all);
    // 멤버 존재 확인
    boolean hasBanana = setOps.isMember("fruits", "banana");
    System.out.println("banana 존재 여부: " + hasBanana);
}
```

---

## 3. Sorted Set

### 자료구조 설명

**Sorted Set(정렬된 집합)은 점수(score)에 따라 정렬되는 고유한 문자열 멤버들의 집합**이다. 각 요소마다 부여된 실수 형태의 점수가 순서를 결정한다.

**활용 예시:**
- 게임 점수 랭킹(리더보드)
- 우선순위 큐
- 시간 기반 정렬 (마지막 접속 시간)

### 주요 명령어

| 명령어 | 설명 |
|--------|------|
| ZADD | 멤버와 점수 추가/업데이트 |
| ZRANGE | 오름차순 범위 조회 |
| ZREVRANGE | 내림차순 범위 조회 |
| ZSCORE | 특정 멤버의 점수 반환 |
| ZRANK/ZREVRANK | 멤버의 순위 반환 |
| ZRANGEBYSCORE | 점수 범위로 멤버 조회 |

### Redis CLI 예시

```bash
redis> ZADD leaderboard 100 "player1"
(integer) 1
redis> ZADD leaderboard 150 "player2"
(integer) 1
redis> ZADD leaderboard 120 "player3"
(integer) 1
redis> ZREVRANGE leaderboard 0 -1 WITHSCORES
1) "player2"
2) "150"
3) "player3"
4) "120"
5) "player1"
6) "100"
redis> ZSCORE leaderboard "player3"
"120"
```

> Sorted Set은 점수를 시간 값(유닉스 타임스탬프)으로 활용하면 **시간순 정렬**이 가능하다.

### Spring RedisTemplate 사용 예시

```java
public void useSortedSetRanking() {
    ZSetOperations<String, String> zSetOps = redisTemplate.opsForZSet();
    // 플레이어 점수 추가
    zSetOps.add("gameRanking", "player1", 100);
    zSetOps.add("gameRanking", "player2", 150);
    zSetOps.add("gameRanking", "player3", 120);
    // 상위 2명의 플레이어 가져오기 (내림차순)
    Set<String> topPlayers = zSetOps.reverseRange("gameRanking", 0, 1);
    System.out.println("Top players: " + topPlayers);
    // 특정 플레이어의 점수 조회
    Double score = zSetOps.score("gameRanking", "player3");
    System.out.println("player3 score: " + score);
}
```

---

## 4. Hash

### 자료구조 설명

**Hash는 하나의 Redis 키에 다수의 필드-값(field-value) 쌍을 저장할 수 있는 레코드 타입**이다. 마치 작은 JSON 객체나 해시 맵을 저장하는 느낌으로, 관련 있는 여러 값을 하나의 묶음으로 관리할 수 있다.

**활용 예시:**
- 사용자 프로필 저장 (name, email, age 등)
- 설정 값 관리
- 여러 카운터를 한데 모아 관리

### 주요 명령어

| 명령어 | 설명 |
|--------|------|
| HSET | 필드-값 설정 |
| HGET | 특정 필드 값 조회 |
| HGETALL | 모든 필드-값 조회 |
| HMGET | 여러 필드 값 동시 조회 |
| HINCRBY | 숫자 필드 증가 |
| HDEL | 필드 삭제 |
| HEXISTS | 필드 존재 여부 확인 |

### Redis CLI 예시

```bash
redis> HSET user:100 name "Alice" age "30" city "Seoul"
(integer) 3
redis> HGET user:100 name
"Alice"
redis> HGETALL user:100
1) "name"
2) "Alice"
3) "age"
4) "30"
5) "city"
6) "Seoul"
redis> HINCRBY user:100 login_count 1
(integer) 1
redis> HGET user:100 login_count
"2"
```

### Spring RedisTemplate 사용 예시

```java
public void useHashExample() {
    HashOperations<String, Object, Object> hashOps = redisTemplate.opsForHash();

    // Hash에 필드-값 설정
    hashOps.put("user:100", "name", "Alice");
    hashOps.put("user:100", "age", 30);

    // 특정 필드 값 조회
    Object name = hashOps.get("user:100", "name");
    System.out.println("Name: " + name);

    // 모든 필드-값 조회
    Map<Object, Object> entries = hashOps.entries("user:100");
    System.out.println("All fields: " + entries);

    // 숫자 필드 증가
    hashOps.increment("user:100", "login_count", 1);
}
```

---

## 5. Bitmap

### 자료구조 설명

**Bitmap은 Redis의 문자열(String) 값을 비트 배열처럼 다루는 기능**이다. 불리언 값들의 집합을 매우 메모리 효율적으로 저장할 수 있다. 하나의 문자열 값으로 최대 2^32개의 비트(약 40억개의 플래그)를 관리할 수 있다.

**활용 예시:**
- 사용자의 일별 접속 기록 (출석 체크)
- 기능 플래그 관리
- 대량 사용자의 상태 추적

### 주요 명령어

| 명령어 | 설명 |
|--------|------|
| SETBIT | 특정 오프셋의 비트를 0 또는 1로 설정 |
| GETBIT | 특정 오프셋의 비트 값 반환 |
| BITCOUNT | 1인 비트의 개수 반환 |
| BITOP | 비트 연산 (AND, OR, XOR 등) |

### Redis CLI 예시

```bash
redis> SETBIT user:1 5 1       # 5번 비트를 1로 설정 (5일차 접속)
(integer) 0
redis> SETBIT user:1 6 1       # 6일차 접속
(integer) 0
redis> GETBIT user:1 5
(integer) 1
redis> GETBIT user:1 7
(integer) 0
redis> BITCOUNT user:1
(integer) 2
```

### Spring RedisTemplate 사용 예시

```java
public void useBitmapExample() {
    ValueOperations<String, String> valueOps = redisTemplate.opsForValue();
    // 특정 비트 설정
    valueOps.setBit("user:1:activeDays", 5, true);
    valueOps.setBit("user:1:activeDays", 6, true);
    // 비트 값 조회
    Boolean day5 = valueOps.getBit("user:1:activeDays", 5);
    Boolean day7 = valueOps.getBit("user:1:activeDays", 7);
    System.out.println("Day5 active: " + day5 + ", Day7 active: " + day7);
    // 1인 비트 개수 세기
    Long totalActiveDays = redisTemplate.execute((RedisCallback<Long>) conn ->
        conn.bitCount("user:1:activeDays".getBytes())
    );
    System.out.println("Total active days: " + totalActiveDays);
}
```

---

## 정리

| 자료구조 | 특징 | 주요 활용 |
|----------|------|----------|
| List | 순서 있는 컬렉션, 양 끝 O(1) | 큐, 스택, 로그 |
| Set | 중복 없는 집합 | 고유 항목 관리, 집합 연산 |
| Sorted Set | 점수 기반 정렬 | 랭킹, 우선순위 큐 |
| Hash | 필드-값 쌍 | 객체 저장, 속성 관리 |
| Bitmap | 비트 배열 | 출석 체크, 상태 플래그 |

---

## 참고

- [[Redis] Redis의 다양한 자료구조와 활용 예시](https://ksh-coding.tistory.com/154)
- [Redis 자료구조와 사용방법](https://gooch123.tistory.com/73)
- [[REDIS] 자료구조 명령어 종류 & 활용 사례 총정리](https://inpa.tistory.com/entry/REDIS-%F0%9F%93%9A-%EB%8D%B0%EC%9D%B4%ED%84%B0-%ED%83%80%EC%9E%85Collection-%EC%A2%85%EB%A5%98-%EC%A0%95%EB%A6%AC)
