---
title: "MDC(Mapped Diagnostic Context)로 요청 단위 로그 추적하기"
date: 2025-12-21 12:00:00 +0900
categories: [Spring]
tags: [spring, logging, mdc, logback, tracing]
---

## 개요

분산 시스템이나 동시 요청이 많은 환경에서 로그만 보고 "이 로그가 어떤 요청에서 나온 건지" 파악하기 어렵다. **MDC(Mapped Diagnostic Context)**는 현재 실행 중인 스레드에 로그용 메타데이터를 저장하여, 요청 단위로 로그를 추적할 수 있게 해주는 메커니즘이다.

---

## 1. 로그의 문제: "문맥(context)"이 없다

예를 들어 이런 로그가 있다면:

```
결제 시작
좌석 예약 완료
결제 실패
```

이 로그들이:
- 같은 요청에서 나온 건지?
- 다른 사용자의 요청이 섞인 건지?
- 어떤 API 흐름인지?

**알 수 없다.** 이걸 해결하기 위해 등장한 개념이 **MDC**이다.

---

## 2. MDC란 무엇인가

### 한 문장 정의

> MDC는 "현재 실행 중인 스레드에 붙는 로그용 메타데이터 저장소"

조금 풀어서 말하면:
- 로그를 찍기 전에 "이 요청의 정보"를 미리 저장해두고
- 로그가 찍힐 때 자동으로 같이 출력되게 하는 장치

---

## 3. MDC는 왜 ThreadLocal 기반인가

### ThreadLocal이란

- **각 스레드마다 따로 보관되는 변수 공간**
- 다른 스레드에서는 절대 접근 불가

```
Thread A → MDC Map A
Thread B → MDC Map B
```

### 웹 요청과의 관계

Spring Boot 웹 서버(Tomcat)에서:
- **요청 1건 = 스레드 1개가 처리**
- 그 스레드 안에서 Controller → Service → Repository → 로그 호출까지 전부 실행됨

> 그래서 **"요청 정보 = 스레드에 붙이면 된다"**

---

## 4. MDC의 실제 동작 흐름

### 1단계: 요청 시작 시 MDC에 값 넣기

```java
MDC.put("requestId", "abc123");
MDC.put("userId", "42");
```

- 이 값들은 **현재 스레드에만 저장됨**
- 코드 어디서든 접근 가능

### 2단계: 어디서든 로그 찍기

```java
log.info("좌석 예약 시작");
```

이때 Logback은 내부적으로 "현재 스레드에 MDC 값 있나?" 확인 후 로그 이벤트에 같이 담음

### 3단계: Encoder가 MDC를 출력

**JSON 로그(LogstashEncoder):**

```json
{
  "requestId": "abc123",
  "userId": "42",
  "message": "좌석 예약 시작"
}
```

> **로그 코드에는 requestId를 안 적었는데 자동으로 포함됨**

### 4단계: 요청 끝나면 반드시 제거

```java
MDC.remove("requestId");
MDC.remove("userId");
```

**왜 제거해야 하나?**
- 서버는 **스레드 풀** 사용
- 스레드는 재사용됨
- 안 지우면 다음 요청에 값이 섞임 (치명적 버그)

---

## 5. 왜 필터(Filter)에서 MDC를 설정하는가

Filter는 **요청 처리의 가장 바깥**이고, Controller보다 먼저 실행되며, Exception이 나도 finally가 보장된다.

```
[Request 시작]
  ↓ Filter (MDC 설정)
    ↓ Controller
      ↓ Service
        ↓ Repository
    ↓ Exception 발생 가능
  ↑ finally (MDC 제거)
[Request 종료]
```

> MDC 설정 위치로 **최적**

---

## 6. 구현: RequestIdFilter

```java
@Component
public class RequestIdFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-Request-Id";

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {

        String requestId = Optional.ofNullable(request.getHeader(HEADER))
            .filter(id -> !id.isBlank())
            .orElse(UUID.randomUUID().toString());

        MDC.put("requestId", requestId);
        response.setHeader(HEADER, requestId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
```

### 핵심 포인트

**1) OncePerRequestFilter 사용**
- 하나의 HTTP 요청당 딱 한 번만 실행 보장
- FORWARD, ERROR, ASYNC 등에서 중복 실행 방지

**2) 클라이언트가 보낸 requestId 존중**
- 외부 시스템(프론트, API Gateway)이 이미 requestId를 만들어 보냈다면 그 흐름을 이어받음

**3) 응답 헤더에 requestId 포함**
- 프론트 개발자가 "이 요청 왜 500 났어요?" 할 때
- "응답 헤더의 X-Request-Id 알려줘" 하면 바로 추적 가능

**4) finally에서 MDC 제거**
- 스레드 재사용 시 값 섞임 방지
- `clear()` 대신 `remove("requestId")` 사용 → 다른 레이어에서 넣은 MDC 보존

---

## 7. logback-spring.xml에서 MDC 사용

### 일반 패턴 로그

```xml
<pattern>
  %d %level %X{requestId} %X{userId} %msg
</pattern>
```

- `%X{}` → MDC 값 참조

### JSON 로그 (LogstashEncoder)

```xml
<encoder class="net.logstash.logback.encoder.LogstashEncoder">
  <includeMdcKeyName>requestId</includeMdcKeyName>
  <includeMdcKeyName>userId</includeMdcKeyName>
</encoder>
```

- MDC Map에서 해당 key만 JSON 필드로 출력
- 로그 수집 시스템에서 필드 기반 검색 가능

---

## 8. JSON stdout + MDC 조합이 중요한 이유

| 조합 | 효과 |
|------|------|
| MDC만 있으면 | 사람이 읽기 힘듦 |
| JSON만 있으면 | 흐름 추적 어려움 |
| **둘 다 있으면** | 구조화된 검색 + 요청 흐름 연결 |

---

## 9. 이 필터로 얻는 효과

### 기술적 효과
- 모든 로그가 **요청 단위로 묶임**
- JSON 로그 / Loki / Grafana에서 필터링 가능
- 멀티 스레드 환경에서도 안전

### 운영적 효과
- "이 에러 요청 ID 주세요" → 바로 추적
- 프론트/QA/운영 커뮤니케이션 단순화
- 장애 시 **원인 범위 급격히 축소**

---

## 10. 확장 가능성

이 구조 위에 바로 얹을 수 있는 것들:

- 인증 필터에서 `MDC.put("userId", …)`
- 도메인 서비스에서 eventId, seatId, orderId 추가
- 스케줄러에는 requestId 대신 **runId** 사용
- Tomcat access log에 `%{X-Request-Id}i`

> **이 필터는 전체 관측 구조의 "기초 체력"**

---

## 정리

1. **MDC**는 스레드 기반 문맥 저장소로 요청 단위 로그 추적 가능
2. **Filter**에서 설정하면 모든 요청에 공통 적용
3. **ThreadLocal** 기반이므로 요청 종료 시 반드시 제거
4. **JSON 로그**와 함께 사용하면 구조화된 검색 가능
5. 장애 대응, 프론트 협업, 추적 디버깅에서 **체감 차이 큼**

---

## 참고

- [[Spring] MDC, 로그 트레이싱하기](https://minnseong.tistory.com/40)
- [[Java] MDC와 스레드 로컬](https://inma.tistory.com/181)
- [Slf4j MDC로 요청별로 식별 가능한 맥락 남기기](https://haon.blog/spring/slf4j-mapped-diagnotics-context/)
