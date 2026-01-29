---
title: "PostgreSQL + JPA ID 생성 전략 - Sequence 기반 최적화"
date: 2025-12-05 12:00:00 +0900
categories: [Database]
tags: [database, postgresql, jpa, sequence, batch-insert, hibernate]
---

## 개요

JPA에서 ID 생성 전략을 선택할 때, 사용하는 데이터베이스의 특성을 이해하는 것이 중요하다. PostgreSQL은 기본적으로 **Sequence 기반 DB**이며, JPA와 함께 사용할 때 Sequence 전략을 적용하면 **batch insert 최적화**와 함께 대량 insert 성능을 크게 개선할 수 있다.

---

## 1. PostgreSQL에서 Sequence가 필요한 이유

PostgreSQL은 IDENTITY도 지원하지만, 기본적으로 Sequence 기반 DB이다. JPA와 사용할 때 Sequence 전략을 적용하면 다음과 같은 장점이 있다.

- ID를 미리 가져와서 메모리에 캐싱할 수 있다
- batch insert 최적화가 가능해진다
- 대량 insert 성능이 IDENTITY 대비 **10배 이상 개선**된다

IDENTITY 전략은 insert 시점에만 ID를 알 수 있으므로 매번 flush가 발생하고, batch insert가 비활성화된다. 대량 insert가 많은 서비스에서는 성능 문제가 된다.

---

## 2. Sequence 전략의 동작 방식

```
1) nextval('seq') 호출로 다음 시퀀스 값 조회
2) allocationSize만큼 ID 범위를 Hibernate가 메모리에 캐싱
3) 엔티티 생성 시 DB 왕복 없이 ID 할당
4) batch insert 활성화
```

**예시: allocationSize = 50**

한 번의 nextval로 1~50 ID를 캐싱 → 50건 insert를 한 번에 처리

---

## 3. BaseEntity 설계

BaseEntity는 ID 필드만 정의하고 **전략은 지정하지 않는다**. 각 도메인 엔티티에서 전략을 선택한다.

```java
@MappedSuperclass
@Getter
@EntityListeners(AuditingEntityListener.class)
public abstract class BaseEntity {

    @Id
    protected Long id;

    @CreatedDate
    protected LocalDateTime createdAt;

    @LastModifiedDate
    protected LocalDateTime modifiedAt;

    protected void setId(Long id) {
        this.id = id;
    }
}
```

---

## 4. 도메인별 Sequence 전략 예시

도메인마다 ID 생성량이 다르므로 별도의 시퀀스를 사용한다.

### Ticket (대량 발급)

```java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "ticket_seq")
@SequenceGenerator(
    name = "ticket_seq",
    sequenceName = "ticket_seq",
    allocationSize = 100
)
private Long id;
```

### User (보통)

```java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "user_seq")
@SequenceGenerator(
    name = "user_seq",
    sequenceName = "user_seq",
    allocationSize = 50
)
private Long id;
```

### Seat (대량 생성)

```java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "seat_seq")
@SequenceGenerator(
    name = "seat_seq",
    sequenceName = "seat_seq",
    allocationSize = 100
)
private Long id;
```

---

## 5. allocationSize 기준

| 도메인 | 특징 | 권장 |
|--------|------|------|
| Ticket | 대량 발급 | 100 |
| Seat | 대량 생성 | 100 |
| User | 보통 | 50 |
| Event | 적은 생성량 | 10 |

allocationSize는 실제 생성량 대비 2~5배 정도로 설정한다.

---

## 6. Hibernate 설정

batch insert를 활성화해야 Sequence 전략의 효과가 나타난다.

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: update
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_inserts: true
        order_updates: true
```

---

## 7. 주의사항

1. **allocationSize와 DB sequence increment가 다르면 문제가 생긴다**
   - Hibernate가 자동 생성하도록 두는 것이 안전하다

2. **서버 재시작 시 ID가 건너뛰는 것은 정상 동작이다**
   - 캐싱한 ID 범위가 폐기되기 때문

3. **BaseEntity에서 생성 전략을 강제하지 말아야 한다**
   - 도메인별로 최적화된 전략을 선택할 수 있게 하기 위함

---

## 정리

1. PostgreSQL은 **Sequence 기반 DB**이므로 Sequence 전략이 최적
2. **allocationSize**로 ID를 미리 캐싱하여 DB 왕복을 줄임
3. **batch insert**를 활성화하면 대량 insert 성능이 크게 개선됨
4. 도메인별 생성량에 따라 **allocationSize를 다르게 설정**
5. BaseEntity에서는 ID 필드만 정의하고 **전략은 하위 엔티티에서 선택**

---

## 참고

- [[Spring/JPA] JPA ID 생성 전략](https://naturecancoding.tistory.com/159)
- [[JPA] JPA에서 PK를 다루는 방법(@Id, @GeneratedValue)](https://soonmin.tistory.com/116)
- [PostgreSQL 개념 및 특징(with MySQL)](https://somaz.tistory.com/297)
- [[JPA] 기본키(PK) 매핑 방법 및 생성 전략](https://gmlwjd9405.github.io/2019/08/12/primary-key-mapping.html)
