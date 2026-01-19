---
title: "Spring Start Here Chapter4 스프링 컨텍스트: 추상화"
date: 2025-04-10 09:00:00 +0900
categories: [Spring]
tags: [java, spring, backend]
---
# CHAPTER4: (스프링 컨텍스트: 추상화)

- 추상화로 구현을 분리하는 것은 클래스 설계를 구현하는 좋은 방법이다. 객체를 분리하면 애플리케이션의 많은 부분에 영향을 주지 않고도 구현을 쉽게 변경할 수 있다. 이런 측면은 애플리케이션을 더 쉽게 확장하고 유지 관리할 수 있게 해 준다.

- 자바에서는 인터페이스로 구현을 분리한다. 또 인터페이스로 구현 간 계약을 정의한다고도 말한다.

- 의존성 주입과 함께 추상화를 사용할 때 스프링은 요청된 추상화의 구현으로 생성된 빈을 검색하는 방법을 알고 있다.

- 스프링에 인스턴스를 생성하고 이 인스턴스를 컨텍스트에 빈으로 추가하도록 지시할 클래스에 스테레오타입 애너테이션을 사용한다. 그러나 인터페이스에는 스테레오타입 애너테이션을 사용하지 않는다.

- 스프링 컨텍스트에 동일한 추상화에 대한 여러가지 구현으로 생성된 빈이 많을 때 어떤 빈을 주입할지 지시하려면 CH3에서 나온 두가지 방법 중 하나를 사용한다.

  1. @Primary 애너테이션을 사용하여 그중 하나를 기본값으로 표시한다.
  2. @Qualifier 애너테이션으로 빈 이름을 지정한 후 스프링에 해당 빈 이름으로 빈을 주입하도록 지시할 수 있다.

- 스테레오 타입 애너테이션을 사용하면 컴포넌트의 책임을 명시적으로 표시할 수 있어 클래스 설계를 일고 이해하기 더 편하게 만들 수 있다.
  - @Service: 서비스 책임이 있는 컴포넌트
  - @Component: 리포지터리 책임이 있는 컴포넌트

<br>

```java
💖 댓글 알림기능 인터페이스 정의(예시코드)
public interface CommentNotificationProxy {
  void sendComment(Comment comment);
}
```

```java
💖 댓글 알림기능 구현체 정의(예시코드)
@Component
public class EmailCommentNotificationProxy implements CommentNotificationProxy {

  @Override
  public void sendComment(Comment comment) {
    System.out.println("Sending notification for comment: " + comment.getText());
  }
}
```

```java
💖 댓글 리포지터리 인터페이스 정의(예시코드)
public interface CommentRepository {
  void storeComment(Comment comment);
}
```

```java
💖 댓글 리포지터리 구현체 정의(예시코드)
@Repository
public class DBCommentRepository implements CommentRepository {

  @Override
  public void storeComment(Comment comment) {
    System.out.println("Storing comment: " + comment.getText());
  }
}
```

```java
💖 댓글 서비스(예시코드)
@Service
public class CommentService {

  private final CommentRepository commentRepository;

  private final CommentNotificationProxy commentNotificationProxy;

  public CommentService(CommentRepository commentRepository,
                        CommentNotificationProxy commentNotificationProxy) {
    this.commentRepository = commentRepository;
    this.commentNotificationProxy = commentNotificationProxy;
  }

  public void publishComment(Comment comment) {
    commentRepository.storeComment(comment);
    commentNotificationProxy.sendComment(comment);
  }
}
```
