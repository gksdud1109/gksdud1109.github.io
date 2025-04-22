---
title: "c++ List Eterator에 관한 질문"
excerpt: "chatgpt님의 답변"

categories:
  - C++

date: 2025-04-22
last_modified_at: 2025-04-22
---
# C++ std::list의 erase와 iterator: 반드시 알아야 할 두 가지 주의점

C++에서 `std::list`를 사용할 때 `erase()`와 `iterator`를 함께 사용할 경우, 아래 두 가지 실수로 인해 **예기치 않은 동작 또는 프로그램 크래시**가 발생할 수 있습니다.

이 포스트에서는 다음 두 가지 상황을 집중적으로 설명합니다:

1. `erase()` 이후 무효화된 iterator를 계속 사용할 경우  
2. 마지막 요소 삭제 후 `end()` iterator를 역참조하는 경우

---

## 1️⃣ erase 이후 iterator를 갱신하지 않고 사용하면?

### 🔻 문제 코드

```cpp
list<int> L = {1, 2, 3};
auto it = next(L.begin(), 1); // it → 2
L.erase(it);                 // 2 삭제
cout << *it << '\n';         // ❌ 미정의 동작(UB)!
```

### ❗ 원인

- `std::list::erase(it)`는 삭제한 노드 **다음 위치의 iterator**를 반환합니다.
- 그러나 기존 iterator는 삭제되었기 때문에 무효화(invalidated)됩니다.
- 무효화된 iterator를 역참조하면 **예측할 수 없는 동작(undefined behavior)** 발생

### ✅ 해결 방법

```cpp
auto it = next(L.begin(), 1); // it → 2
it = L.erase(it);             // 2 삭제 → it → 3
if (it != L.end()) {
  cout << *it << '\n';        // 안전하게 출력
}
```

---

## 2️⃣ 마지막 요소를 erase하면 반환 iterator는 end()

### 🔻 문제 코드

```cpp
list<int> L = {10, 6, 1, 2, 5};
auto t = next(L.begin(), 4);  // t → 5

// 마지막 요소 삭제
t = L.erase(t);               // t → L.end()
cout << *t << '\n';           // ❌ end() iterator 역참조 → UB
```

### ❗ 원인

- 마지막 요소를 `erase()`하면, 반환값은 `list.end()`가 됩니다.
- `end()`는 실제 요소가 아닌, 리스트의 종료 지점을 나타내므로 **역참조 불가**입니다.

### ✅ 해결 방법

```cpp
auto t = next(L.begin(), 4);  // t → 5
t = L.erase(t);               // 5 삭제 → t == L.end()

if (t != L.end()) {
  cout << *t << '\n';
} else {
  cout << "더 이상 원소가 없습니다." << '\n';
}
```

---

## 💡 전체 실습 예제

```cpp
#include <bits/stdc++.h>
using namespace std;

int main(void)
{
  list<int> L = {1, 2};
  list<int>::iterator t = L.begin(); // t → 1

  L.push_front(10);                 // 10 1 2
  cout << *t << '\n';               // 1
  L.push_back(5);                   // 10 1 2 5
  L.insert(t, 6);                   // 10 6 1 2 5

  t++;                              // t → 2
  t++;                              // t → 5
  t = L.erase(t);                   // 5 삭제 → t == end()

  if (t != L.end())
    cout << *t << '\n';
  else
    cout << "마지막 요소를 삭제했습니다." << '\n';

  for (int i : L)
    cout << i << ' ';
  cout << '\n';
}
```

---

## ✅ 정리

| 상황 | 잘못된 예시 | 안전한 예시 |
|------|-------------|-------------|
| erase 후 iterator 사용 | `erase(it); *it;` | `it = erase(it); *it;` |
| 마지막 요소 삭제 후 | `erase(last); *it;` | `if (it != end()) *it;` |


**항상 erase 후 iterator를 갱신하고, end() 체크를 습관화하세요!**
이것만 지켜도 list와 관련된 버그 대부분을 방지할 수 있습니다 💡