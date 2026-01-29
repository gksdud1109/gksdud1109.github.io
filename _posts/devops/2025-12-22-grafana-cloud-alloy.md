---
title: "Grafana Cloud + Alloy 로그 수집 구성 가이드"
date: 2025-12-22 12:00:00 +0900
categories: [DevOps]
tags: [devops, grafana, loki, alloy, logging, monitoring]
---

## 개요

EC2 단일 인스턴스에서 Spring Boot + Redis + Nginx만으로도 리소스가 민감한 상황에서, 장애 분석을 위한 로그 수집 시스템이 필요했다. **관측 도구 때문에 서비스가 느려지면 안 된다**는 원칙 하에, Grafana Cloud + Grafana Alloy 조합을 선택했다.

---

## 1. 도입 배경

### 제약 조건

- EC2 단일 인스턴스, 메모리 여유 적음
- Spring Boot + Redis + Nginx만으로도 리소스 민감
- 장애 분석은 로그 기반 상관관계 추적이 핵심
- 관측 도구 때문에 서비스가 느려지면 안 됨

### 선택한 원칙

- 서버는 **로그를 stdout으로만 출력**
- 로그 수집/저장/검색은 **외부 Managed 서비스** 사용
- EC2에는 **가벼운 에이전트(Alloy)만** 실행

---

## 2. 전체 구조

```
Spring Boot
  └─ JSON 로그 (stdout)
        ↓
Grafana Alloy (Agent)
  └─ 로그 수집
        ↓
Grafana Cloud Logs (Loki)
        ↓
Grafana UI (Explore / Dashboard)
```

| 컴포넌트 | 역할 |
|----------|------|
| Spring Boot | 로그 생성만 |
| Alloy | 로그 수집 + 전송만 |
| Grafana Cloud | 로그 저장 + 조회 |

> **EC2에 Loki / Prometheus / Grafana를 직접 띄우지 않는다**

---

## 3. 사전 준비 사항

### 3-1. Grafana Cloud 계정

- Grafana Cloud Free 플랜
- Logs(Loki) 활성화

**필요 정보:**
- Loki Push URL
- User ID
- API Token (Logs:Write 권한)

### 3-2. Spring Boot 로그 전제 조건

이미 적용 완료된 상태 기준:

- logback-spring.xml
  - perf / prod: JSON stdout
- MDC 필드 포함
  - runId
  - requestId
  - eventId (스케줄러/도메인)
- docker logs에서 JSON 로그 확인 가능

> Alloy는 stdout만 읽는다 → **애플리케이션 코드 수정 불필요**

---

## 4. Grafana Alloy 구성

### 4-1. 실행 방식

- Docker 컨테이너 1개
- 애플리케이션 컨테이너의 stdout 로그 파일을 마운트해서 읽음

### 4-2. docker-compose 예시

```yaml
services:
  alloy:
    image: grafana/alloy:latest
    container_name: grafana-alloy
    volumes:
      - ./alloy/config.alloy:/etc/alloy/config.alloy
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
    command:
      - run
      - /etc/alloy/config.alloy
    restart: always
```

### 4-3. Alloy 설정 파일 (config.alloy)

```hcl
logging {
  level = "info"
}

loki.source.docker "containers" {
  host = "unix:///var/run/docker.sock"
}

loki.write "grafana_cloud" {
  endpoint {
    url = "https://<LOKI_PUSH_URL>"
    basic_auth {
      username = "<USER_ID>"
      password = "<API_TOKEN>"
    }
  }
}

loki.relabel "app_logs" {
  rule {
    source_labels = ["container_name"]
    target_label  = "container"
  }
  rule {
    target_label = "job"
    replacement  = "waitfair"
  }
}

loki.pipeline "pipeline" {
  stage.json {}
}

loki.source.docker "containers" {
  forward_to = [loki.pipeline.pipeline.receiver]
}

loki.pipeline "pipeline" {
  forward_to = [loki.relabel.app_logs.receiver]
}

loki.relabel "app_logs" {
  forward_to = [loki.write.grafana_cloud.receiver]
}
```

**핵심 포인트:**
- Docker stdout 로그를 직접 읽음
- JSON 로그 파싱 (stage.json)
- job=waitfair 라벨 고정
- Grafana Cloud Loki로 전송

---

## 5. Grafana에서 로그 조회

### 5-1. 기본 조회

Grafana → Explore → Logs

```
{job="waitfair"}
```

### 5-2. 스케줄러 단위 조회

```
{job="waitfair"} |= "SCHED_START"
```

```
{job="waitfair"} |= "QueueEntry"
```

### 5-3. runId 기반 전체 흐름 추적

```
{job="waitfair", runId="94237a0a-66ba-4f8e-bbf7-54ad626c9a72"}
```

- 스케줄러 1회 실행 전체 흐름 확인
- START → ITEM → END / FAIL 추적 가능

### 5-4. 특정 이벤트만 추적

```
{job="waitfair", eventId="3"}
```

- Queue / Seat / Ticket 흐름을 이벤트 단위로 확인

---

## 6. 운영 시 기대 효과

- **서버 접속 없이도 로그 분석 가능**
- 스케줄러/배치/비동기 작업 흐름 가시화
- 장애 발생 시 즉시 파악 가능:
  - "언제"
  - "어떤 job이"
  - "얼마나 처리했고"
  - "왜 실패했는지"

---

## 7. 현재 범위에서 하지 않는 것

이번 단계에서 의도적으로 제외한 항목:

| 항목 | 제외 이유 |
|------|-----------|
| EC2 내 Loki 직접 설치 | 리소스 부담 |
| Prometheus 상시 운영 | 리소스 부담 |
| OpenTelemetry / Tracing | 복잡도 대비 효과 낮음 |
| Alert Rule 구성 | 현재 단계에서 불필요 |

> **지금은 로그 기반 관측이 충분**

---

## 정리

1. **서버 리소스 최소화**: EC2에는 Alloy만 실행
2. **외부 서비스 활용**: Grafana Cloud로 저장/조회 위임
3. **MDC 기반 추적**: runId, eventId로 흐름 추적
4. **JSON 로그**: 파싱 및 필터링 용이
5. **운영 부담 최소화**: 기존 Docker 환경에 Alloy만 추가

---

## 참고

- [Logging/Grafana Loki 통한 로그 수집하기](https://medium.com/@dudwls96/logging-grafana-loki-%ED%86%B5%ED%95%9C-%EB%A1%9C%EA%B7%B8-%EC%88%98%EC%A7%91%ED%95%98%EA%B8%B0-d57ba1b75ab3)
- [Grafana Alloy 기본 사용 및 Prometheus & Loki 연동](https://hackjsp.tistory.com/78)
- [번역) grafana alloy 튜토리얼](https://velog.io/@wy9295/%EB%B2%88%EC%97%AD-grafana-alloy-%ED%8A%9C%ED%86%A0%EB%A6%AC%EC%96%BC)
- [Grafana Alloy로 애플리케이션의 Metrics와 Logs 수집하기](https://velog.io/@yechan-kim/Grafana-Alloy%EB%A1%9C-%EC%95%A0%ED%94%8C%EB%A6%AC%EC%BC%80%EC%9D%B4%EC%85%98%EC%9D%98-Metrics%EC%99%80-Logs-%EC%88%98%EC%A7%91%ED%95%98%EA%B8%B0)
