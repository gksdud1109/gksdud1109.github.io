---
title: "[Spring]JdbcTemplate Rowmapper사용"
date: 2025-04-02 09:00:00 +0900
categories: [Spring]
tags: [java, spring, backend]
---
# AI 너 진짜 개쩐다...

# **JDBC Template에서 RowMapper 완벽 이해하기**

JDBC Template을 사용하여 데이터베이스에서 데이터를 조회할 때, 결과를 객체로 변환하는 역할을 하는 것이 `RowMapper<T>`입니다.

이 글에서는 `RowMapper`가 **어떤 역할을 하는지**를 중점적으로 설명하고, 익명 클래스와 람다식을 비교하여 **더 깔끔한 코드 작성법**을 소개하겠습니다.

---

## **📌 RowMapper란?**

`RowMapper<T>`는 **JDBC의 결과 집합(ResultSet)의 한 행(row)을 특정 객체로 변환하는 인터페이스**입니다.

- **목적:** SQL 조회 결과를 Java 객체로 변환
- **주로 사용되는 곳:** `JdbcTemplate.query()` 메서드에서 결과를 매핑할 때
- **핵심 메서드:** `T mapRow(ResultSet rs, int rowNum)`
  - `rs`: 현재 행(Row)의 데이터
  - `rowNum`: 현재 처리 중인 행 번호 (사용하지 않아도 됨)

---

## **🔹 코드 분석**

```java
public List<Purchase> findAllPurchases() {
    String sql = "SELECT * FROM purchase";

    RowMapper<Purchase> purchaseRowMapper = (r, i) -> {
        Purchase rowObject = new Purchase();
        rowObject.setId(r.getInt("id"));
        rowObject.setProduct(r.getString("product"));
        rowObject.setPrice(r.getBigDecimal("price"));
        return rowObject;
    };

    return jdbc.query(sql, purchaseRowMapper);
}
```

이 코드에서 `RowMapper<Purchase>`는 **SQL 결과를 `Purchase` 객체로 변환하는 역할**을 합니다.

`jdbc.query(sql, purchaseRowMapper)`를 호출하면 다음과 같이 동작합니다:

1. SQL `"SELECT * FROM purchase"` 실행
2. 결과 집합(ResultSet)의 각 행에 대해 `RowMapper`의 `mapRow()` 메서드 호출
3. 변환된 `Purchase` 객체를 리스트에 담아 반환

---

## **🔹 RowMapper 구현 방법 비교**

### **1. 기존 방식 (익명 클래스 사용)**

람다식을 사용하기 전에는 `RowMapper`를 익명 클래스로 구현해야 했습니다.

```java
RowMapper<Purchase> purchaseRowMapper = new RowMapper<Purchase>() {
    @Override
    public Purchase mapRow(ResultSet r, int i) throws SQLException {
        Purchase rowObject = new Purchase();
        rowObject.setId(r.getInt("id"));
        rowObject.setProduct(r.getString("product"));
        rowObject.setPrice(r.getBigDecimal("price"));
        return rowObject;
    }
};
```

💡 **단점:** 코드가 길고 가독성이 떨어짐

---

### **2. 람다식 적용 (간결한 표현)**

```java
RowMapper<Purchase> purchaseRowMapper = (r, i) -> {
    Purchase rowObject = new Purchase();
    rowObject.setId(r.getInt("id"));
    rowObject.setProduct(r.getString("product"));
    rowObject.setPrice(r.getBigDecimal("price"));
    return rowObject;
};
```

💡 **장점:** 익명 클래스를 제거하고 코드가 더 간결해짐

### **람다식 분석**

```java
(r, i) -> {
    Purchase rowObject = new Purchase();
    rowObject.setId(r.getInt("id"));
    rowObject.setProduct(r.getString("product"));
    rowObject.setPrice(r.getBigDecimal("price"));
    return rowObject;
};
```

- `(r, i) -> { ... }`
  → **람다식(익명 함수) 문법**
- `(r, i)`
  → `RowMapper`의 `mapRow(ResultSet r, int rowNum)` 메서드의 매개변수
  - `r`: `ResultSet` 객체 (SQL 결과 행)
  - `i`: 현재 처리 중인 행(row)의 번호 (사용하지 않아도 됨)
- `{ ... }`
  → **람다식 본문:** `ResultSet`의 데이터를 읽어 `Purchase` 객체로 변환

💡 **즉, 익명 클래스를 간결하게 람다식으로 표현한 것!**

---

## **🔹 최종 정리**

| 코드                         | 설명                                            |
| ---------------------------- | ----------------------------------------------- |
| `RowMapper<T>`               | SQL 조회 결과를 특정 객체로 변환하는 인터페이스 |
| `mapRow(ResultSet r, int i)` | 각 행을 객체로 변환하는 메서드                  |
| 익명 클래스 사용             | 구현이 길고 가독성이 떨어짐                     |
| 람다식 사용                  | 코드가 간결해지고 유지보수가 쉬워짐             |
| `jdbc.query(sql, rowMapper)` | SQL 실행 후 변환된 객체 리스트 반환             |

---

## **✅ 결론: RowMapper를 람다식으로 구현하자!**

- `RowMapper`는 **SQL 결과를 객체로 변환하는 핵심 인터페이스**
- 익명 클래스보다 **람다식을 사용하면 코드가 더 간결**해짐
- **JDBC Template에서 데이터 조회 시 필수적으로 사용됨**

🚀 **결론:** `RowMapper`를 람다식으로 사용하여 가독성과 유지보수성을 높이자!
