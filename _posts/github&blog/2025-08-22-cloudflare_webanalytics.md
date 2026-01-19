---
title: "깃허브 블로그에 방문자 수 집계 집어넣기"
date: 2025-08-22 09:00:00 +0900
categories: [DevOps]
tags: [devops]
---
## 클라우드 플레어에서 내 도메인 등록

[클라우드 플레어 대시보드](https://dash.cloudflare.com/edc31ae7c6fe8d905c5cfdecbcf9536e/web-analytics/sites)

- 클라우드 플레어 계정을 생성하고 아래와 같은 경로로 Web Analytics를 제공받을 내 웹사이트 등록

[![2025-08-22-16-12-04.png](https://i.postimg.cc/xTWMBLww/2025-08-22-16-12-04.png)](https://postimg.cc/GHx4yThK)

- github.io는 cloudflare에서 관리하는 도메인이 아니기 때문에 아래와 같은 안내가 뜬다.

[![2025-08-22-16-14-03.png](https://i.postimg.cc/ZR26Z39v/2025-08-22-16-14-03.png)](https://postimg.cc/62V8f8fB)

- 이 호스트네임은 우리게 아니지만 JS Snippet을 너의 웹사이트에 넣으면 분석해준다는 뜻이다.

- snippet발급전에 가입한 계정인증을 해줘야 다음단계로 넘어간다

- JS Snippet을 \_includes > head > custom.html에 붙여넣기 해주면 끝!

> 💡 Jekyll을 사용하는 Minimal Mistakes테마는 레이아웃 구조가 <br/> > \_layouts/default.html -> \_includes/head/custom.html안에 있는 내용 끄집어오도록 되어있다

- 🔽Minimal Mistakes default.html 코드

{% raw %}

```html
<head>
  {% include head.html %} {% include head/custom.html %}
</head>
```

{% endraw %}

## 방문자 수 집계를 하고 싶었지만

> ✨할 수 있는 줄 알았는데... <br/>
> 무료 JS 스니펫 버전은 API를 제공하지 않는다고 한다

<hr>

참고: [Cloudflare Docs](https://developers.cloudflare.com/web-analytics/get-started/)
