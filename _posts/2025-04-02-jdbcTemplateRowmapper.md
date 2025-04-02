---
title: "[Spring]JdbcTemplate Rowmapper사용"
excerpt: "Spring Start Here_JdbcTemplate사용예제 중 Rowmapper에대한_AI의 친절한 해설"

categories:
  - Spring
  - AI

date: 2025-04-02
last_modified_at: 2025-04-02
---

# AI 성능 쩐다...

# **JDBC Template에서 **``** 람다식 이해하기**

JDBC Template을 사용하여 데이터베이스에서 데이터를 조회할 때, 결과를 객체로 변환하는 역할을 하는 것이 `RowMapper<T>`입니다.

이 글에서는 다음 코드의 **람다식 부분을 집중적으로 설명**하고, 익명 클래스와 비교하여 람다식의 장점을 이해해보겠습니다.

---

## **📌 코드 분석**

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

이 코드는 ``** 테이블의 모든 데이터를 조회**하여 `Purchase` 객체 리스트로 변환하는 역할을 합니다.

특히 `RowMapper`를 **람다식**으로 구현한 부분이 핵심입니다.

---

## **🔹 **``** 람다식 분석**

### **1. **``**란?**

- `RowMapper<T>`는 **SQL 조회 결과(ResultSet)의 한 행(row)을 특정 객체(**``**)로 변환하는 인터페이스**입니다.
- 주로 데이터베이스 테이블의 각 행을 Java 객체로 매핑할 때 사용됩니다.

### **2. 기존 방식 (**``**)**

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

💡 `RowMapper<T>`의 `mapRow(ResultSet r, int rowNum)` 메서드는 **SQL 결과의 각 행을 **``** 객체로 변환**하는 역할을 합니다.

---

## **🔹 람다식 **``** 설명**

### **람다식으로 변환된 **``

```java
RowMapper<Purchase> purchaseRowMapper = (r, i) -> {
    Purchase rowObject = new Purchase();
    rowObject.setId(r.getInt("id"));
    rowObject.setProduct(r.getString("product"));
    rowObject.setPrice(r.getBigDecimal("price"));
    return rowObject;
};
```

- `(r, i) -> { ... }`\
  → **람다식(익명 함수) 문법**
- `(r, i)`\
  → `RowMapper`의 `mapRow(ResultSet r, int rowNum)` 메서드의 매개변수
  - `r`: `ResultSet` 객체 (SQL 결과 행)
  - `i`: 현재 처리 중인 행(row)의 번호 (사용하지 않아도 됨)
- `{ ... }`\
  → **람다식 본문:** `ResultSet`의 데이터를 읽어 `Purchase` 객체로 변환

💡 **즉, **``** 익명 클래스를 간결하게 람다식으로 표현한 것!**

---

## **🔹 **``** 동작 방식**

```java
return jdbc.query(sql, purchaseRowMapper);
```

- `jdbc.query(sql, rowMapper)`\
  → `purchase` 테이블의 모든 행을 가져와 `RowMapper`를 통해 `Purchase` 객체 리스트로 변환
- 실행 과정:
  1. `"SELECT * FROM purchase"` SQL 실행
  2. `RowMapper`가 각 행을 `Purchase` 객체로 변환
  3. 변환된 `Purchase` 객체를 리스트(`List<Purchase>`)에 담아 반환

---

## **🔹 최종 정리**

| 코드                         | 설명                                                                     |
| ---------------------------- | ------------------------------------------------------------------------ |
| `(r, i) -> { ... }`          | `RowMapper`의 `mapRow(ResultSet r, int rowNum)` 메서드를 람다식으로 표현 |
| `r.getInt("id")`             | 현재 행에서 `id` 컬럼 값을 가져옴                                        |
| `r.getString("product")`     | `product` 컬럼 값을 가져옴                                               |
| `r.getBigDecimal("price")`   | `price` 컬럼 값을 `BigDecimal`로 가져옴                                  |
| `jdbc.query(sql, rowMapper)` | SQL 실행 후 결과를 `Purchase` 리스트로 변환                              |

---

## **✅ 람다식이 적용된 이유**

- **코드가 간결해짐**
- **불필요한 **``** 익명 클래스 제거**
- **가독성이 좋아지고 유지보수가 쉬워짐**

---

### **🚀 한눈에 보는 전환 과정**

```java
// (1) 기존 익명 클래스 방식
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

// (2) 람다식으로 변환 (더 간결하게!)
RowMapper<Purchase> purchaseRowMapper = (r, i) -> {
    Purchase rowObject = new Purchase();
    rowObject.setId(r.getInt("id"));
    rowObject.setProduct(r.getString("product"));
    rowObject.setPrice(r.getBigDecimal("price"));
    return rowObject;
};
```

📌 **결론:** `RowMapper`의 `mapRow()` 메서드를 람다식으로 표현하면 코드가 더 깔끔해지고 유지보수가 쉬워진다! 🚀
