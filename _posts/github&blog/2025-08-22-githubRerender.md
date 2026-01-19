---
title: "깃허브 렌더링(빌드)만 다시 돌리는 방법"
date: 2025-08-22 09:00:00 +0900
categories: [DevOps]
tags: [devops]
---
## 가장 간단한 트리거 방법

1. 빈 커밋으로 빌드 트리거

```bash
git commit --allow-empty -m "chore: trigger pages rebuild"
git push origin main   # 브랜치명이 main이 아니라면 해당 이름으로
```

2. 타임스탬프 '터치' 커밋

```bash
date > .rebuild
git add .rebuild
git commit -m "chore: trigger rebuild"
git push
```

💡 .rebuild 같은 파일은 .gitignore에 추가해두면 이후에도 간편하게 재사용 가능.

## GitHub UI에서 바로 재빌드

3. Actions에서 재실행

- Actions 탭 → pages-build-deployment(혹은 Pages 관련 워크플로우) 선택
- Re-run all jobs 버튼 클릭 → 즉시 재빌드

[![2025-08-22-12-46-08.png](https://i.postimg.cc/PqCP3Y09/2025-08-22-12-46-08.png)](https://postimg.cc/f3hzktzf)

4. Pages 설정에서 재시도

- Settings → Pages → Build history에서 최근 빌드 선택
  - Retry(또는 Re-run) 버튼 클릭
- !!!할수도 있다는데 내 화면에서는 안나옴

[![2025-08-22-12-49-26.png](https://i.postimg.cc/J76SmXFP/2025-08-22-12-49-26.png)](https://postimg.cc/V5tKWJmC)

## 내용/설정 변경으로 강제 트리거

5. \_config.yml에 ‘무해한’ 수정

```yaml
# _config.yml
# 맨 아래에 빌드에 영향 없는 주석 한 줄 추가
# rebuild: 2025-08-22
```

커밋/푸시하면 재빌드 된다.

6. 포스트 메타데이터 미세 수정

\_posts/\*.md의 front matter(예: last_modified_at)에 현재 시간을 넣고 커밋/푸시.

로컬에서 먼저 확인 (선택)

```bash
bundle install         # 처음이라면
bundle exec jekyll build
bundle exec jekyll serve
```

- 빌드 오류가 없고 로컬 미리보기까지 정상이라면, 위의 방법 중 하나로 원격 재빌드 트리거
- \_site/는 리포에 커밋하지 않음(빌드 산출물)

빠른 체크리스트 (렌더링 문제 재발 방지)

- \_config.yml에 테마/플러그인이 GitHub Pages에서 지원되는지 확인
- GitHub Pages 사용 시 보통 gem "github-pages" 사용 권장
- 빌드 브랜치/폴더 설정 확인
- Settings → Pages에서 Source가 main(또는 gh-pages)이고, 폴더가 /(root) 또는 /docs인지
- 캐시 관련
- 리포에 \_site/, .jekyll-cache/가 커밋돼 있지 않도록 .gitignore 확인
- 액션 실패 로그
- Actions → 실패한 run을 열어 Jekyll 에러 메시지 확인(테마/플러그인 버전 불일치가 흔함)
