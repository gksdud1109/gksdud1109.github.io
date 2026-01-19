---
title: "Spring Start Here Chapter2 스프링 컨텍스트: 빈정의 요약"
date: 2025-03-29 09:00:00 +0900
categories: [Spring]
tags: [java, spring, backend]
---
# CHAPTER2: (스프링 컨텍스트: 빈정의)

- 스프링에서 가장 먼저 배워야 할 것은 스프링 컨텍스트(context)에 객체 인스턴스(빈, Bean)를 추가하는 것이다. 스프링 컨텍스트는 스프링이 관리하기 원하는 인스턴스를 담을 바구니라고 할 수 있다. 스프링은 컨텍스트에 추가된 인스턴스만 볼 수 있다.

- 스프링 컨텍스트에 빈을 추가하는 방법은 세 가지다.<br>

  1. @Bean 애너테이션
  2. 스테레오타입 애너테이션
  3. 프로그래밍 방식

## @Bean 애너테이션

1번 @Bean 애너테이션 방식을 사용하면 어떤 종류의 객체 인스턴스도 빈으로 추가할 수 있으며, 심지어 같은 종류의 다수 인스턴스도 추가할 수 있다. 이런 관점에서 2번 스테레오타입 애너테이션을 사용하는 것보다 유연하지만, 컨텍스트에 추가될 개별 인스턴스에 대해 구성 클래스에서 별도의 메서드를 만들어야 하므로 더 많은 코드를 작성해야 한다.

```Java
@Configuration  // 프로젝트의 구성(config) 클래스 정의
public class ProjectConfig{

  @Bean   // 빈을 반환하는 매서드 정의
  @Primary // 기본 빈으로 정의
  Parrot parrot1(){
    var p = new Parrot();
    p.setName("Miki");
    return p;
  }
  @Bean // 동일한 타입 빈 여러개 정의
  Parrot parrot2(){
    var p = new Parrot();
    p.setName("Koko");
    return p;
  }
}
```

```Java
public class Main{
  public static void main(String[] args){
    var context =
    new AnnotationConfigApplicationContext(ProjectConfig.class);
    // 스프링 컨텍스트 인스턴스가 생성될 때 구성 클래스를 매개변수로 전송하여 스프링이 이를 사용하도록 지시한다.

    Parrot p = context.getBean(Parrot.class);
    Parrot p2 = context.getBean("parrot2", Parrot.class);
  }
}
```

> 기본적으로 스프링은 @Bean으로 주석이 달린 메서드 이름을 빈 이름으로 사용한다.

> @Bean(name="miki")와 같이 이름(name) 또는 값(value) 속성 중 하나로 빈에 다른 이름을 지정할 수도 있다.

> 동일 타입의 여러 빈 사이에 모호성을 해결하려면 @Primary 애너테이션으로 기본(primary) 빈을 만들 수 있다. 사용자가 이름을 지정하지 않을 때

## 스테레오타입 애너테이션

스테레오타입 애너테이션을 사용하면 특정 애너테이션이 있는 애플리케이션 클래스만을 위한 빈을 생성할 수 있다. 이 구성 방식은 코드를 덜 작성하므로 구성을 더욱 편하게 읽을 수 있다.

> 💖 Parrot 클래스에 대해 @Component애너테이션을 사용하면 스프링은 이 클래스의 인스턴스를 생성하고 스프링 컨텍스트에 추가한다.💖

```Java
@Component
public class Parrot{

  private String name;

  // getter & setter 생략
}
```

> 💖 @ComponentScan의 basePackages 속성으로 스프링에 스테레오타입 애너테이션이 지정된 클래스를 찾을 위치를 알려준다.💖

```Java
@Configuration
@ComponentScan(basePackages="main")
public class ProjectConfig{
}
```

> 스프링이 빈을 생성한 직후에 @PostConstruct 애너테이션으로 정의된 메서드를 호출하도록해서 생성자 실행을 완료한 후 원하는 작업을 수행토록 지시할 수 있다.

## 프로그래밍 방식

registerBean() 메서드를 사용해 스프링 컨텍스트에 빈을 추가하는 로직을 재정의하여 구현할 수 있다. \*스프링 5 이상에서만 사용가능

```Java
public class Main {

  public static void main(String[] args) {
      var context = new AnnotationConfigApplicationContext(ProjectConfig.class);

      Parrot x = new Parrot();
      x.setName("Kiki");

      Supplier<Parrot> parrotSupplier = () -> x;

      //context.registerBean("parrot1", Parrot.class, parrotSupplier);

      context.registerBean("parrot1",
              Parrot.class,
              parrotSupplier,
              bc -> bc.setPrimary(true));

      Parrot p = context.getBean(Parrot.class);

      System.out.println(p.getName());
  }
}
```
