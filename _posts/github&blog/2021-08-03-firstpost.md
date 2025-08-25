---
title: "깃허브 블로그 첫 포스팅"
excerpt: "jekyll테마 적용 이후 포스팅하는 방법 정리"

categories:
  - blog
tags:
  - [blog, jekyll, Github, Git]

toc: true
toc_sticky: true

date: 2021-08-03
last_modified_at: 2021-08-03
---

# 첫 포스팅

## TODO

- html, css, javascript 처음부터 복습하기
- 포스트 여러번 진행하면서 빨리 익숙해지기
- CS지식들 복습하면서 해당 내용들 포스트 올리기
- change
  <br>

# 포스트 절차

- \_posts 폴더 생성

1. 포스트 파일 생성

   yyyy-mm-dd-title.md 형식의 파일을 \_posts 폴더에 생성 확장자는 md이어야 한다.

2. 머릿말 작성

   - title : 포스트의 제목을 큰따옴표 안에 작성한다.
   - excerpt : 블로그의 포스트 목록에서 보여지는 포스트 소개 글. 역시 큰 따옴표 안에 작성해준다.
   - categories : 포스트의 카테고리를 지정해준다. 해당 카테고리 페이지로 이동하는 url이 붙는다.
   - tags : [] 대괄호안에 작성하여 포스트의 태그를 지정해 줄 수 있다.
   - toc : true로 설정하면 포스트의 헤더들만 보여주는 목차가 보여지게 된다.
   - toc_sticky : true로 설정하면 toc이 스크롤을 따라 다니게 된다.
   - date : 글을 처음 작성한 날짜.
   - last_modified_at : 글을 마지막으로 수정한 날짜.

   이 밖에 더 고급옵션이 있는데 추후에 liquid언어와 함께 정리하겠다.

3. 포스트 내용을 마크다운 문법으로 작성한다.
   `---`로 끝난 이후부터 포스트 본문을 마크다운 문법으로 작성하면 된다. jekyll은 HTML과 Markdown을 지원하므로 편한 문법을 사용해 작성하면 된다.

4. 작성한 포스트 내용을 미리 보기  
   VS code에서 사용할 수 있는 `Preview` 기능을 사용하면 포스트 결과물을 미리 보며 작성할 수 있다. 굉장히 편리하다.

5. 포스트 파일을 git push하여 서버에 업로드.  
   git bash에서 직접 커밋하고 푸시하거나 VS code에서 바로 업로드 하는 방법이 있다.
