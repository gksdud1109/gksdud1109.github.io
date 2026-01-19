---
title: "Spring Start Here Chapter6 스프링 AOP로 애스펙트 사용"
date: 2025-04-12 09:00:00 +0900
categories: [Spring]
tags: [java, spring, backend]
---
# CHAPTER6: 스프링 AOP로 애스펙트 사용

> 애프펙트는 메서드 호출을 가로채는 객체로 가로챈 메서드를 실행하기 전후나 아예 대체 로직을 실행시킬 수도 있다.<br>
> 이를 통해 비즈니스 구현에서 코드 일부를 분리하여 앱을 더 쉽게 유지 관리 할 수 있다.

- 애스펙트를 사용하면 메서드 실행과 함께 실행되는 로직을 해당 메서드에서 완전히 분리해서 작성할 수 있다. 이렇게 하면 코드를 읽는 사람은 비즈니스 구현과 관련된 부분만 볼 수 있다.

- 하지만 애스펙트는 위험한 도구가 될 수 있다. 애스펙트로 코드를 오버엔지니어링하면 앱을 유지 관리하기가 어렵다. 모든 곳에 애스펙트를 사용할 필요는 없다.
  따라서 사용할 때는 실제로 구현에 도움이 되는지 확인해야 한다.

- 애스펙트는 트랜잭션 및 보안 메서드 같은 많은 필수 스프링 기능을 지원한다.

## 스프링에서 애스펙트 작동 방식

> 애스펙트는 사용자가 선택한 특정 메서드를 호출할 때 프레임워크가 실행하는 로직의 일부다. 애스펙트를 정의할 때는 다음 사항을 정의한다.
>
> - 애스펙트(aspects): 특정 메서드를 호출할 때 스프링이 실행하길 원하는 코드는 무엇인지 정의한다.
> - 어드바이스(advice): 앱이 언제 이 애스펙트 로직을 실행해야 하는지 정의한다.
> - 포인트컷(pointcut): 프레임워크가 어떤 메서드를 가로채기(intercept)해서 해당 애스펙트를 실행해야 하는지 정의한다.

애스펙트 용어와 함께 애스펙트 실행을 트리거하는 이벤트를 정의해주는 조인트 포인트(jointpoint)의 개념도 있다. 스프링에서는 항상 이런 이벤트는 메서드 호출이다.<br>

스프링이 메서드 호출을 가로채서 애스펙트 로직을 적용할 때는 실제 메서드 대신 애스펙트 로직을 호출하는 객체, 실제 빈 대신 프록시(proxt)객체를 제공한다 <br>
애스펙트를 실행해 컨텍스트에서 빈을 얻을 때는 언제나 빈 대신 프록시 객체를 받게 된다. 이렇게 감싸는 방식을 위빙(weaving)이라고 한다.

## 스프링 AOP를 사용한 애스펙트 구현

- 스프링에서 애스펙트를 정의하려면 애스펙트 로직을 구현하는 클래스에 @Aspect 애너테이션을 추가한다. 하지만 스프링은 이 클래스의 인스턴스를 관리해야 하므로 스프링 컨텍스트에 해당 타입의 빈도 추가해야 한다는 점을 기억하라.

- 스프링에 어떤 메서드를 가로채야 하는지 알려주려면 AsepctJ 포인트컷 표현식을 사용한다. 이런 표현식을 어드바이스(advise) 애너테이션에 값으로 작성한다. 스프링은 다섯가지 어드바이스 애너테이션(@Around, @Before, @After, @AfterThrowing, @AfterReturning)을 제공한다. 대부분은 가장 강력한 @Around를 사용한다.

1. 스프링 앱에서 애스펙트 활성화

```java
@Configuration
@ComponentScan(basePackages="services")
@EnableAspectJAutoProxy // 스프링 앱에서 애스펙트 메커니즘을 활성화 한다.
public class ProjectConfig{
}
```

2. 애스펙트 클래스를 생성하고 스프링 컨텍스트에 애스펙트 빈 추가

```java
@Aspect
public class LoggingAspect{
  public void log(){
    //로깅 기능 구현
  }
}
```

3. 어드바이스 애너테이션으로 스프링에 언제 어떤 메서드를 가로챌지 지시

```java
@Aspect
public class LoggingAspect{

  @Around("execution(* services.*.*(...))") // 어떤 메서드를 가로챌지 정의
  public void log(ProceedingJoinPoint joinPoint){
    joinPoint.proceed(); // 실제 가로채는 메서드에 위임한다.
  }
}
```

> <a href="https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html">포인트 컷 가이드 문서</a> <br>

```java
execution(* services.\*.\*(..))<br>
-> execution((가로챌 메서드의 리턴 타입) (패키지).(클래스).(메서드 이름)(매개변수) )
```

4. 애스펙트 로직 구현

```java
@Aspect
public class LoggingAspect {
  private Logger logger = Logger.getLogger(LoggingAspect.class.getName());

  @Around("execution(* services.*.*(..))")
  public void log(ProceedingJoinPoint joinPoint) throws Throwable {
    logger.info("Method will execute");
    joinPoint.proceed();
    logger.info("Method executed");
  }
}
```

ProceedingJoinPoint 매개변수는 가로챈 메서드를 나타낸다. 이 매개변수를 사용하여 가로챈 메서드와 관련된 모든 정보(매개변수, 메서드 이름, 대상 객체 등)를 가져올 수 있다.

```java
@Aspect
public class LoggingAspect {
  private Logger logger = Logger.getLogger(LoggingAspect.class.getName());

  @Around("execution(* services.*.*(..))")
  public Object log(ProceedingJoinPoint joinPoint) throws Throwable {
    String methodName = joinPoint.getSignature().getName();
    Object [] arguments = joinPoint.getArgs();

    logger.info("Method" + methodName +
                "with parameters " + Arrays.asList(arguments) + " will execute");

    Object returnedByMethod = joinPoint.proceed();

    logger.info("Method executed and returned " + returnedByMethod);

    return returnedByMethod;
  }
}
```

### 애너테이션된 메서드 가로채기

```java
@Retnetion(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface ToLog{
}
```

위 코드에서 커스텀 애너테이션의 선언이 있다. 기본적으로 자바에서는 실행 중에 애너테이션을 가로챌 수 없다. 따라서 리텐션 정책을 RUNTIME으로 설정하여 다른 사람이 애너테이션을 가로챌 수 있도록 명시적으로 지정해야 한다. @Target 애너테이션은 이 애너테이션을 사용할 수 있는 언어 요소를 지정한다.

```java
@Service
public class CommentService {
  private Logger logger = Logger.getLogger(CommentService.class.getName());

  public void publishComment(Comment comment){
    logger.info("Publishing comment: " + comment.getText());
  }

  @ToLog
  public void deleteComment(Comment comment){
    logger.info("Deleting comment: " + comment.getText());
  }
}
```

```java
@Aspect
public class LoggingAspect {
  private Logger logger = Logger.getLogger(LoggingAspect.class.getName());

  @Around("@annotation(ToLog)")
  public Object log(ProceedingJoinPoint joinPoint) throws Throwable){
    // 애스펙트 동작
  }
}
```

### Around 이외의 어드바이스 애너테이션

- @Before: 가로채기된 메서드가 실행되기 전에 애스펙트 로직을 정의하는 메서드를 호출한다.

- @AfterReturning: 메서드가 성공적으로 반환된 후 애스펙트 로직을 정의하는 메서드를 호출하고 반환된 값을 애스펙트 메서드에 매개변수로 제공한다.
  가로채기된 메서드가 예외를 던지면 애스펙트 메서드는 호출되지 않는다.

- @AfterThrowing: 가로채기된 메서드가 예외를 던지면 애스펙트 로직을 정의하는 메서드를 호출하고 예외 인스턴스를 애스펙트 메서드의 매개변수로 전달한다.

- @After: 메서드가 성공적으로 반환했는지 또는 예외를 던졌는지 여부와 관계없이 가로채기된 메서드 실행 후에만 애서펙트 로직을 정의하는 메서드를 호출한다.

## 애스펙트 실행 체인

> 여러 애스펙트가 동일한 메서드의 호출을 가로챌 수 있다. 이 경우 @Order 애너테이션을 사용하여 애스펙트가 실행할 순서를 정의하면 좋다. 스프링은 동일한 실행 체인에 있는 두 애스펙트가 호출되는 순서를 보장하지 않는다.
