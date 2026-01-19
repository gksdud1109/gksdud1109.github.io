---
title: "Spring Start Here Chapter3 스프링 컨텍스트: 빈 작성 요약"
date: 2025-03-29 09:00:00 +0900
categories: [Spring]
tags: [java, spring, backend]
---
# CHAPTER3: (스프링 컨텍스트: 빈 작성)

> 스프링 컨텍스트는 프레임워크가 관리하는 객체를 유지하는 데 사용하는 앱 메모리 공간이다. 프레임워크가 제공하는 기능으로 스프링 컨텍스트에서 보강해야 하는 모든 객체를 추가해야 한다.

- 앱을 구현할 때는 한 객체에서 다른 객체를 참조해야 한다. 이것으로 한 객체가 자신의 책임을 실행할 때 다른 객체에 작업을 위임할 수 있다. 이 동작을 구현하려면 스프링 컨텍스트에서 빈 간 관계를 설정해야 한다.

- 다음 후술할 1, 2, 3번 세가지 방식 중 하나를 사용하여 두 빈 간 관계를 설정할 수 있다.

## 1. 구성 파일에서 정의된 빈 간 관계 구현(메서드 직접 참조)

> 빈을 생성하는 메서드에서 다른 빈을 생성하는 @Bean 애너테이션된 메서드를 직접 참조한다. 스프링은 컨텍스트에서 사용자가 빈을 참조한다는 것을 알고 있으며, 빈이 이미 있을 때는 동일한 메서드를 다시 호출하여 다른 인스턴스를 생성하지 않는 대신 컨텍스트에서 기존 빈에 대한 참조를 반환한다.

```java
@Configuration
public class ProjectConfig {
  @Bean
  public Parrot parrot(){
    Parrot p = new Parrot();
    p.setName("Koko");
    return p;
  }

  @Bean
  public Person persion(){
    Person p = new Person();
    p.setName("Ella");
    p.setParrot(parrot());  // parrot 빈 직접 참조
    return p;
  }
}
```

## 2. 구성 파일에서 정의된 빈 간 관계 구현(@Bean 메서드의 매개변수로 빈 와이어링)

> @Bean애너테이션된 메서드에 매개변수를 정의한다. 스프링은 이 @Bean이 지정된 메서드에서 매개변수를 발견하면 해당 매개변수 타입의 빈을 컨텍스트에서 검색하고 해당 빈을 매개변수 값으로 전달한다.

```java
@Configuration
public class ProjectConfig{
  @Bean
  public Parrot parrot(){
    Parrot p = new Parrot();
    p.setName("Koko");
    return p;
  }

  @Bean
  public Person person(Parrot parrot){    //스프링이 parrot빈 주입
    Person p = new Person();
    p.setName("Ella");
    p.setParrot(parrot);
    return p;
  }
}
```

## 3. @Autowired 애너테이션을 사용한 빈주입

> @Autowired 애너테이션을 사용하는 방식은 다시 세가지로 나뉜다.

### 클래스 필드를 이용한 값 주입

> 컨텍스트에서 빈을 주입하도록 스프링에 지시하려는 클래스의 필드에 @Autowired애너테이션을 추가한다. 이 방식은 예제와 개념 증명(Poc)에서 자주 사용된다.

    ```java
    @Component
    public class Person{
      private String name = "Ella";

      @Autowired
      private Parrot parrot; //초깃값 없이는 final필드를 정의할 수 없으므로 final로 선언은 불가

      // ...
    }
    ```

### 생성자로 값 주입

> 빈을 생성하기 위해 스프링이 호출할 생성자에 @Autowired애너테이션을 추가한다. 스프링은 컨텍스트에 있는 다른 빈을 생성자의 매개변수로 주입한다.이 방식은 실제 코드에서 가장 많이 사용된다.

    ```java
    @Component
    public class Person{
      private String name = "Ella";
      private final Parrot parrot;  // final로 설정하여 초기화 후 값 변경을 불가하게 할 수 있다.

      @Autowired  // 스프링 버전 4.3부터 생성자가 하나만 있을 시에는 @Autowired애너테이션을 생략가능하다.
      public Person(Parrot parrot) {
        this.parrot = parrot;
      }

      // ...
    }
    ```

### setter를 이용한 의존성 주입 사용

> 스프링이 컨텍스트에서 빈을 주입하려는 속성의 setter에 @Autowired애너테이션을 추가한다. (잘 사용안함)

<br>
<hr>

> 스프링이 클래스의 속성이나 메서드 또는 생성자 매개변수를 사용하여 값이나 참조를 제공하도록 허용할 때는 스프링이 IoC원칙으로 지원되는 기술인 DI를 사용한다고 할 수 있다.

## 순환 의존성

> 서로 의존하는 빈 두 개를 생성하면 순환 의존성이 발생한다. 스프링은 순환 의존성이 있는 빈은 생성할 수 없고, 예외를 발생시키며 실행은 실패한다. 빈을 구성할 때는 순환 의존성을 피해야 한다.

```java
@Component
public class Person {
  private final Parrot parrot;

  @Autowired
  public Person(Parrot parrot) {
    this.parrot = parrot;
  }

  // ...
}
```

```java
@Component
public class Parrot {
  private String name = "Koko";
  private final Person person;

  @Autowired
  public Parrot(Person person) {
    this.person = person;
  }

  // ...
}
```

> 위의 구성으로 앱을 실행하면 아래와 같은 에러가 발생한다. 두 빈은 서로 의존하고 있으므로 초기화에 서로가 필요하다. 스프링은 교착 상태(deadlock)에 빠진다.

![image](https://github.com/user-attachments/assets/58ce1d0f-f1b9-457f-9ed9-9590de1fe3eb)

## 스프링 컨텍스트에서 여러 빈 중 선택하기

> 컨텍스트에 타입이 동일한 빈이 두 개 이상 있을 때 스프링은 그중 어떤 빈을 주입해야 하는지 정하지 못한다. 주입해야 할 인스턴스를 스프링에 알려 주는 방법은 다음과 같다.

1. @Primary 애너테이션 사용

2. @Qualifier 애너테이션 사용

```java
@Configuration
public class ProjectConfig{
  @Bean
  public Parrot parrot1(){
    Parrot p = new Parrot();
    p.setName("Koko");
    return p;
  }
  @Bean
  public Parrot parrot2(){
    Parrot p = new Parrot();
    p.setName("Miki");
    return p;
  }

  @Bean
  public Person person(@Qualifier("parrot2") Parrot parrot){
    Person p = new Person();
    p.setName("Ella");
    p.setParrot(parrot);
    return p;
  }
}
```

```java
@Component
public class Person{
  private String name = "Ella";
  private final Parrot parrot;

  public Person(@Qualifier("parrot2") Parrot parrot) {
    this.parrot = parrot;
  }
  // ...
}
```
