---
title: "[JavaBasic]BigDecimal의 사용이유"
date: 2025-04-02 09:00:00 +0900
categories: [Spring]
tags: [java, backend]
---
# AI 성능 쩐다...

# **Java에서 `double` 대신 `BigDecimal`을 사용해야 하는 이유**

자바에서 부동 소수점(`double`, `float`)을 사용하면 **소수점 정밀도 문제가 발생**할 수 있습니다. 이 문제는 부동 소수점 연산이 **이진(2진) 부동 소수점 표기법(IEEE 754 표준)**을 사용하여 숫자를 표현하는 방식에서 비롯됩니다.

이를 방지하려면 **`BigDecimal`을 사용**하여 **정확한 소수 연산**을 수행해야 합니다.

---

## **1. `double`과 `float`의 문제점: 부동 소수점 오차**

### **🔹 `double` 연산의 오류 예제**

```java
public class FloatingPointTest {
    public static void main(String[] args) {
        double a = 0.1;
        double b = 0.2;
        double sum = a + b;
        System.out.println("0.1 + 0.2 = " + sum);
    }
}
```

#### **출력 결과:**

```
0.1 + 0.2 = 0.30000000000000004
```

❌ **문제: `0.1 + 0.2`가 `0.3`이 아니라 `0.30000000000000004`로 출력됨!**

이러한 **부동 소수점 오차**는 컴퓨터가 **실수를 2진수로 변환하는 과정에서 발생**합니다.

---

## **2. 왜 `double`과 `float`에서 오차가 발생할까?**

### **(1) `double`과 `float`은 이진수(2진수)로 저장됨**

컴퓨터는 **모든 숫자를 2진수(0과 1)로 변환**하여 저장합니다. 그런데 **10진수의 일부 소수 값은 2진수로 정확하게 변환할 수 없음**.

#### **예제: 0.1을 2진수로 변환**

- 0.1을 2진수로 변환하면 **`0.000110011001100110011...` (무한 반복)**
- 하지만 `double`은 **64비트**만 사용하므로, **0.1을 정확하게 저장할 수 없음**.
- 결과적으로 **근사값(0.10000000000000000555...)만 저장**됨.

➡ **즉, `0.1`과 `0.2` 모두 2진수로 완벽하게 표현할 수 없고, 연산할 때 오차가 발생함**.

---

## **3. `BigDecimal`은 어떻게 문제를 해결할까?**

### **(1) `BigDecimal`은 10진수(Decimal) 기반의 연산 수행**

`BigDecimal`은 **10진수(Decimal) 기반으로 숫자를 저장**하기 때문에 `double`과 달리 오차 없이 소수를 정확하게 표현할 수 있음.

#### **예제: `BigDecimal`을 사용한 정확한 연산**

```java
import java.math.BigDecimal;

public class BigDecimalTest {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("0.1");
        BigDecimal b = new BigDecimal("0.2");
        BigDecimal sum = a.add(b);

        System.out.println("0.1 + 0.2 = " + sum);
    }
}
```

🔹 **출력 결과:**

```
0.1 + 0.2 = 0.3
```

✔ **정확하게 `0.3`이 출력됨!**
✔ `BigDecimal`은 **10진수 기반의 연산을 수행하기 때문에 반올림 오차가 발생하지 않음**.

---

## **4. `BigDecimal` 사용 시 주의할 점**

### **(1) `new BigDecimal(double)` 사용 금지**

❌ 다음 코드는 여전히 부동 소수점 오차를 포함할 수 있음.

```java
BigDecimal a = new BigDecimal(0.1);  // 잘못된 방식!
```

🔹 **문제점**: `new BigDecimal(0.1)`은 **이미 `double`의 부동 소수점 오차를 포함**한 값을 사용하여 `BigDecimal`을 생성하기 때문에 **오차가 그대로 유지됨**.

✅ **올바른 방법:**

```java
BigDecimal a = new BigDecimal("0.1");  // 문자열을 사용!
```

➡ **문자열(`"0.1"`)을 사용하여 생성하면 정확한 값이 저장됨**.

---

### **(2) `BigDecimal` 연산은 반드시 `add()`, `subtract()`, `multiply()`, `divide()` 사용**

❌ `+`, `-`, `*`, `/` 연산자를 사용할 수 없음.

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

// BigDecimal은 + 연산자를 사용할 수 없음 ❌
BigDecimal sum = a + b; // 컴파일 오류!
```

✅ **올바른 방법:**

```java
BigDecimal sum = a.add(b);  // 덧셈
BigDecimal diff = a.subtract(b);  // 뺄셈
BigDecimal product = a.multiply(b);  // 곱셈
BigDecimal quotient = a.divide(b, 10, BigDecimal.ROUND_HALF_UP);  // 나눗셈 (반올림 필요)
```

---

## **5. 언제 `BigDecimal`을 사용해야 할까?**

### ✅ `BigDecimal`을 사용해야 하는 경우:

- **금융 계산 (돈, 가격, 세금 등)**
- **과학적 계산 (소수점 정밀도가 중요한 경우)**
- **정확한 연산이 필요한 모든 경우**

### ❌ `BigDecimal`을 사용하지 않아도 되는 경우:

- **고속 연산이 필요한 경우 (`double`이 속도가 더 빠름)**
- **소수점 정밀도가 크게 중요하지 않은 경우**
- **메모리 사용량이 중요한 경우 (`BigDecimal`은 `double`보다 메모리를 많이 사용)**

---

## **6. 결론**

|                   | `double`, `float`          | `BigDecimal`                   |
| ----------------- | -------------------------- | ------------------------------ |
| **정확성**        | 부동 소수점 오차 발생      | 소수점 정밀도 유지             |
| **연산 속도**     | 빠름                       | 느림                           |
| **메모리 사용량** | 적음                       | 많음                           |
| **사용 사례**     | 일반적인 계산, 과학적 연산 | 금융, 화폐, 정확한 소수점 연산 |

### **👉 `double`은 속도가 빠르지만 정밀도가 낮고, `BigDecimal`은 느리지만 정밀도가 높음.**

**정확한 소수점 연산이 필요할 때는 `BigDecimal`을 사용해야 함!** 🚀
