---
title: "logback-spring.xml 설정 - 환경별 로그 구성과 JSON 로깅"
date: 2025-12-21 13:00:00 +0900
categories: [Spring]
tags: [spring, logging, logback, json, mdc, grafana]
---

## 개요

Spring Boot 애플리케이션에서 로그 설정은 **logback-spring.xml**을 통해 세밀하게 제어할 수 있다. 특히 로컬/개발 환경과 운영 환경에서 서로 다른 로그 형식이 필요할 때, 프로파일별로 구분하여 설정하면 효과적이다. 이 글에서는 환경별 로그 구성과 JSON 로깅, MDC 연동 방법을 정리한다.

---

## 1. 왜 환경별 로그 설정이 필요한가

### 로컬/개발 환경

- 사람이 직접 콘솔에서 로그를 읽음
- 컬러풀하고 가독성 좋은 형식 필요
- 파일로도 저장하여 이전 로그 확인

### 운영 환경 (perf/prod)

- 로그 수집 시스템(Grafana/Loki)이 로그를 수집
- JSON 형식으로 구조화된 로그 필요
- MDC 필드 기반 검색 가능해야 함
- 사람이 직접 서버에서 로그를 "눈으로 읽는 경우는 드묾"

> **운영 로그는 사람이 직접 보는 게 아니라, 쿼리해서 본다**

---

## 2. 전체 설정 파일

```xml
<configuration>

    <!-- =========================
         공통 설정
         ========================= -->
    <springProperty scope="context"
                    name="APP_NAME"
                    source="spring.application.name"
                    defaultValue="waitfair"/>

    <!-- =========================
         LOCAL / DEV
         - Spring Boot 기본 콘솔 로그 그대로
         - 파일로만 rolling
         ========================= -->
    <springProfile name="local,dev">

        <!-- Spring Boot 기본 console appender 그대로 사용 -->
        <include resource="org/springframework/boot/logging/logback/defaults.xml"/>
        <include resource="org/springframework/boot/logging/logback/console-appender.xml"/>

        <!-- 로컬 디버깅용 파일 로그 -->
        <appender name="FILE"
                  class="ch.qos.logback.core.rolling.RollingFileAppender">
            <file>logs/dev.log</file>
            <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
                <fileNamePattern>logs/dev.%d{yyyy-MM-dd}.log</fileNamePattern>
                <maxHistory>7</maxHistory>
            </rollingPolicy>
            <encoder>
                <pattern>
                    %d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n
                </pattern>
            </encoder>
        </appender>

        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
            <appender-ref ref="FILE"/>
        </root>
    </springProfile>

    <!-- =========================
         PERF / PROD
         - JSON stdout only
         ========================= -->
    <springProfile name="perf,prod">

        <appender name="JSON_CONSOLE"
                  class="ch.qos.logback.core.ConsoleAppender">
            <encoder class="net.logstash.logback.encoder.LogstashEncoder">
                <!-- 고정 필드 -->
                <customFields>
                    {"app":"${APP_NAME}"}
                </customFields>

                <!-- MDC에서 가져올 필드 -->
                <includeMdcKeyName>requestId</includeMdcKeyName>
                <includeMdcKeyName>userId</includeMdcKeyName>
                <includeMdcKeyName>eventId</includeMdcKeyName>
                <includeMdcKeyName>seatId</includeMdcKeyName>
                <includeMdcKeyName>orderId</includeMdcKeyName>
            </encoder>
        </appender>

        <!-- 불필요한 로그 줄이기 -->
        <logger name="org.hibernate.SQL" level="WARN"/>
        <logger name="org.hibernate.orm.jdbc.bind" level="WARN"/>
        <logger name="org.springframework.web" level="INFO"/>

        <root level="INFO">
            <appender-ref ref="JSON_CONSOLE"/>
        </root>
    </springProfile>

</configuration>
```

---

## 3. 설정 상세 설명

### 3.1 공통 설정

```xml
<springProperty scope="context"
                name="APP_NAME"
                source="spring.application.name"
                defaultValue="waitfair"/>
```

- `application.yml`의 `spring.application.name` 값을 Logback에서 변수로 사용
- `${APP_NAME}`으로 JSON 로그에 앱 이름 포함

### 3.2 LOCAL/DEV 프로파일

**Spring Boot 기본 콘솔 로그 재사용:**

```xml
<include resource="org/springframework/boot/logging/logback/defaults.xml"/>
<include resource="org/springframework/boot/logging/logback/console-appender.xml"/>
```

- IntelliJ에서 보던 컬러풀하고 가독성 좋은 로그 그대로 유지
- 패턴을 따로 정의하지 않음

**파일 로그 추가:**

```xml
<appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/dev.log</file>
    <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
        <fileNamePattern>logs/dev.%d{yyyy-MM-dd}.log</fileNamePattern>
        <maxHistory>7</maxHistory>
    </rollingPolicy>
</appender>
```

- 하루 단위로 파일 분리
- 최대 7일 보관, 오래된 로그 자동 삭제

### 3.3 PERF/PROD 프로파일

**JSON stdout Appender:**

```xml
<appender name="JSON_CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="net.logstash.logback.encoder.LogstashEncoder">
```

- 출력 대상은 stdout
- docker logs, Alloy, Cloud 로그 수집기가 읽음

**고정 필드:**

```xml
<customFields>
    {"app":"${APP_NAME}"}
</customFields>
```

- 모든 로그에 항상 포함됨

**MDC 필드 포함:**

```xml
<includeMdcKeyName>requestId</includeMdcKeyName>
<includeMdcKeyName>userId</includeMdcKeyName>
<includeMdcKeyName>eventId</includeMdcKeyName>
```

Filter나 Service에서 `MDC.put("requestId", "...")`하면 자동으로 JSON 필드로 출력됨

**출력 예시:**

```json
{
  "level": "INFO",
  "message": "seat reserved",
  "app": "waitfair",
  "requestId": "a1b2c3",
  "userId": "42",
  "eventId": "10"
}
```

**불필요한 로그 제한:**

```xml
<logger name="org.hibernate.SQL" level="WARN"/>
<logger name="org.hibernate.orm.jdbc.bind" level="WARN"/>
```

- 운영 로그에서 SQL 한 줄 한 줄, 바인딩 값은 노이즈
- WARN 이상만 남기도록 제한

---

## 4. 전체 동작 흐름

### LOCAL / DEV

```
로그 발생
 → Spring Boot 기본 콘솔 포맷으로 출력 (사람 친화)
 → 동시에 logs/dev.log에 rolling 저장
```

### PERF / PROD

```
로그 발생
 → MDC에서 requestId/userId/... 추출
 → JSON으로 구조화
 → stdout 출력
 → Alloy / Grafana Cloud / Loki가 수집
```

---

## 5. 의존성 추가

JSON 로깅을 위해 `logstash-logback-encoder` 의존성이 필요하다.

```gradle
implementation 'net.logstash.logback:logstash-logback-encoder:7.4'
```

---

## 6. MDC와 JSON 로그 조합의 효과

### 기존 텍스트 로그의 문제

- 사람 눈으로 보기는 편하지만
- 시스템이 구조적으로 해석하기 어려움

### JSON 로그 + MDC의 장점

- 로그가 key-value 구조
- 로그 수집 시스템에서 정확히 필터링 가능:
  - `userId=test-user`
  - `eventId=45`
  - `requestId=abc123`

> 사람이 읽기 위한 로그가 아니라, **문제 상황을 빠르게 찾아내기 위한 로그**

---

## 7. 운영 환경에서 JSON 로그가 불편하지 않은 이유

실제 운영 패턴:

| 환경 | 로그 형식 | 확인 방법 |
|------|----------|----------|
| local/dev | Spring Boot 기본 콘솔 | 직접 눈으로 확인 |
| perf/prod | JSON stdout | Grafana/Loki에서 쿼리 |

**서버에 직접 접속해서 로그를 "눈으로 읽는 경우는 매우 드묾"**

---

## 정리

1. **환경별 프로파일**로 로그 형식을 분리
2. **LOCAL/DEV**: Spring Boot 기본 콘솔 + 파일 롤링
3. **PERF/PROD**: JSON stdout + MDC 필드 포함
4. **LogstashEncoder**로 구조화된 JSON 로그 생성
5. 로그 수집 시스템에서 **필드 기반 검색** 가능
6. 불필요한 로그는 **logger level 제한**으로 줄이기

---

## 참고

- [Springboot에서 Logback 설정하기](https://velog.io/@woosim34/Springboot-Logback-%EC%84%A4%EC%A0%95%ED%95%B4%EB%B3%B4%EA%B8%B0)
- [spring boot 로그 파일 남기는 방법](https://wildeveloperetrain.tistory.com/302)
- [Spring - Logback 설정하기](https://backtony.tistory.com/33)
- [Spring Boot 로깅 - logback-spring.xml 설정 및 Grafana Loki 연동](https://hechan2.tistory.com/25)
