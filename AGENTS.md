# Blog Migration Guide

## Project Info
- **Theme**: Chirpy (jekyll-theme-chirpy)
- **Target URL**: https://gksdud1109.github.io
- **Previous Theme**: Minimal Mistakes (sunrise skin)

## Owner Info
- **Name**: 정한영
- **GitHub**: gksdud1109
- **Email**: vectorh532@gmail.com
- **Instagram**: 0one_zer0

---

## Category Structure (6 categories, 78 posts)

| Category | Posts | Content |
|----------|-------|---------|
| **Spring** | 21 | Spring Boot, JPA, QueryDSL, JDBC, Java |
| **React** | 17 | React, JavaScript Deep Dive, Frontend |
| **Algorithm** | 16 | BOJ, Programmers, Data Structure, C++ |
| **Kotlin** | 10 | Kotlin basics and advanced |
| **DevOps** | 9 | GitHub, Blog, Networking, etc. |
| **Database** | 5 | MySQL, SQL, RDBMS |

---

## Writing New Posts

### Front Matter Template (Chirpy Format)
```yaml
---
title: "Post Title"
date: YYYY-MM-DD HH:MM:SS +0900
categories: [CategoryName]
tags: [tag1, tag2, tag3]
---
```

### Category Guide
- **Spring**: Spring Boot, JPA, QueryDSL, Java backend
- **React**: React, JavaScript, frontend development
- **Algorithm**: Problem solving (BOJ, Programmers), data structures
- **Kotlin**: Kotlin language
- **DevOps**: Blog settings, GitHub, tools, networking
- **Database**: SQL, MySQL, database design

### Tag Examples by Category
```
Spring: spring, java, jpa, querydsl, backend
React: react, javascript, frontend
Algorithm: algorithm, boj, programmers, problem-solving, data-structure
Kotlin: kotlin, programming
DevOps: devops, github, blog
Database: database, sql, mysql
```

---

## Useful Commands

```bash
# Install dependencies
bundle install

# Local server (requires rbenv)
eval "$(rbenv init -)" && bundle exec jekyll serve

# Build only
eval "$(rbenv init -)" && bundle exec jekyll build
```

---

## File Naming Convention
```
YYYY-MM-DD-descriptive-title.md

Examples:
2025-01-20-spring-jpa-basics.md
2025-01-20-react-hooks-guide.md
2025-01-20-boj-1234-solution.md
```

---

## Migration Complete
- [x] Chirpy theme setup
- [x] Ruby 3.3.0 via rbenv
- [x] 78 posts migrated
- [x] Categories reorganized (11 → 6)
- [x] Front matter converted to Chirpy format
- [x] Build verified
