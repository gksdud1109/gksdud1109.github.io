---
title: "vault-ledger 학습 가이드 — EVM 인덱서와 무결성 감사 시스템 심층 해설"
date: 2026-03-06 12:00:00 +0900
categories: [Blockchain]
tags: [go, ruby, rails, blockchain, evm, erc-20, merkle-tree, docker, idempotency, postgresql]
---

> **AI-Augmented EVM Indexer & Auditable Ledger** — Go와 Ruby를 조합하여 Sepolia 네트워크의 ERC-20 입금 이벤트를 수집하고, 멱등성 보장 원장과 Merkle Tree 기반 변조 탐지를 구현한 시스템.

이 프로젝트는 기술 학습목적으로 AI를 활용해 빠르게 설계하고 구현(Vibe Coding)했지만, 그 안의 설계 선택들은 단순하지 않다. 멱등성, 해시 체인 기반 Audit Trail, Go/Ruby 하이브리드 아키텍처 — 적절한 도구를 골라 시스템을 설계하고 검증하는 과정이 이 프로젝트의 핵심이다.

이 가이드는 Go, Ruby, 블록체인이 처음인 사람도 **"이 파일이 왜 존재하고 어떻게 연결되는가"** 를 이해할 수 있도록 구조적 선택의 이유까지 함께 설명한다.

---

# vault-ledger 학습 가이드

> 작성자 본인을 포함해 :) Go, Ruby, 블록체인이 모두 처음인 분을 위한 심층 해설서. <br>
> 이 프로젝트의 모든 파일이 왜 존재하고 어떻게 연결되는지 설명합니다.

---

## 목차

1. [이 프로젝트가 하는 일 (큰 그림)](#1-이-프로젝트가-하는-일-큰-그림)
2. [블록체인 기초 — 코드를 읽기 전에 알아야 할 개념](#2-블록체인-기초)
3. [프로젝트 구조 한눈에 보기](#3-프로젝트-구조-한눈에-보기)
4. [인프라 — Docker와 환경변수](#4-인프라--docker와-환경변수)
5. [Go 서비스 (chain-indexer-go) 완전 해설](#5-go-서비스-chain-indexer-go-완전-해설)
6. [Ruby 서비스 (admin-rails) 완전 해설](#6-ruby-서비스-admin-rails-완전-해설)
7. [데이터베이스 — 테이블 설계와 이유](#7-데이터베이스--테이블-설계와-이유)
8. [v0 → v1 → v2 진화 스토리](#8-v0--v1--v2-진화-스토리)
9. [데이터가 흐르는 전체 경로 (end-to-end)](#9-데이터가-흐르는-전체-경로-end-to-end)
10. [핵심 알고리즘 해설 — Merkle Tree & 해시 체인](#10-핵심-알고리즘-해설--merkle-tree--해시-체인)

---

## 1. 이 프로젝트가 하는 일 (큰 그림)

### 한 문장 요약

> **"특정 지갑 주소로 들어오는 모든 ERC-20 토큰 입금 내역을 자동으로 수집·저장하고, 그 데이터가 변조되지 않았음을 수학적으로 증명할 수 있는 시스템"**

### 현실 세계 비유

은행 입금 통장을 생각해보세요.

| 현실 세계 | vault-ledger |
|----------|-------------|
| 은행 서버 | 블록체인 노드 (Sepolia) |
| 입금 내역 | ERC-20 Transfer 이벤트 |
| 통장 기록 | `deposits` 테이블 |
| 은행 앱 조회 | admin-rails API |
| 감사 보고서 | audit_anchors + Merkle 증명 |

### 왜 이런 시스템이 필요한가?

블록체인은 공개 장부이지만, "내 지갑으로 들어온 입금"을 실시간으로 추적하려면 직접 노드에 계속 물어봐야 합니다. 이 프로젝트는 그 과정을 자동화하고, 수집된 데이터가 나중에 누군가 DB를 직접 수정해도 탐지할 수 있도록 암호학적 무결성 증명을 추가합니다.

---

## 2. 블록체인 기초

> 코드에 등장하는 개념들만 골라서 설명합니다.

### 블록(Block)이란?

블록체인은 이름 그대로 블록들이 체인처럼 연결된 구조입니다.

```
[블록 #1000] → [블록 #1001] → [블록 #1002] → ...
```

각 블록에는 그 시점에 발생한 **트랜잭션들의 묶음**이 들어있습니다. 블록은 약 12초마다 하나씩 생성됩니다 (Ethereum 기준).

코드에서 블록 번호가 이렇게 등장합니다:
```go
// chain-indexer-go/cmd/main.go
latestBlock, err := client.EthBlockNumber()  // "현재 최신 블록 번호가 뭐야?"
```

### 트랜잭션(Transaction)이란?

누군가가 블록체인에 보내는 요청입니다. "A가 B에게 100 토큰을 보낸다"는 행위가 트랜잭션이 됩니다. 각 트랜잭션은 고유한 해시값(`tx_hash`)을 가집니다.

```
tx_hash 예시: 0x4f8a3c9b2e1d7f6a...  (64자리 16진수)
```

### 이벤트(Event) / 로그(Log)란?

스마트 컨트랙트가 트랜잭션을 처리하면서 남기는 **기록지**입니다. 영수증(Receipt)에 찍히는 도장 같은 것입니다.

ERC-20 토큰의 전송은 항상 `Transfer` 이벤트를 남깁니다:

```
Transfer(address from, address to, uint256 amount)
```

이 이벤트가 이 프로젝트가 수집하는 핵심 데이터입니다.

### Topics란?

이벤트는 데이터를 **Topics**와 **Data**로 나눠서 저장합니다.

```
Topic[0] = 이벤트 종류 식별자 (Transfer의 고유 서명 해시)
Topic[1] = from 주소 (보낸 사람)
Topic[2] = to 주소 (받는 사람)
Data     = amount (금액)
```

코드에서 이렇게 사용합니다:
```go
// chain-indexer-go/internal/rpc/client.go
transferSig := "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
// 이 긴 숫자는 "Transfer(address,address,uint256)"를 Keccak-256으로 해시한 값입니다.
// 전 세계 모든 ERC-20의 Transfer 이벤트는 이 값이 Topic[0]에 있습니다.

topics := []interface{}{
    transferSig,    // Topic[0]: "Transfer 이벤트만 봐"
    nil,            // Topic[1]: from 주소는 누구든 상관없어
    targetToTopic,  // Topic[2]: to 주소는 반드시 내 지갑이어야 해
}
```

### ERC-20이란?

이더리움 위에서 동작하는 **토큰 표준**입니다. USDC, USDT, DAI 같은 토큰들이 모두 이 표준을 따릅니다. ERC-20을 따르면 모든 토큰이 같은 방식으로 `Transfer` 이벤트를 발생시키기 때문에, 이 프로젝트 하나로 어떤 ERC-20 토큰이든 추적할 수 있습니다.

### Sepolia란?

이더리움의 **테스트넷**입니다. 실제 돈이 오가는 메인넷과 달리, 테스트용 ETH를 무료로 받아서 개발/테스트할 수 있습니다. 코드 동작 방식은 메인넷과 완전히 동일합니다.

### JSON-RPC란?

블록체인 노드와 통신하는 방식입니다. 노드에 HTTP 요청을 보내서 데이터를 조회합니다.

```
요청: { "method": "eth_blockNumber", "params": [] }
응답: { "result": "0x13c7a8" }   ← 16진수로 옵니다
```

이 프로젝트에서 사용하는 두 가지 RPC 메서드:
- `eth_blockNumber`: 현재 최신 블록 번호 조회
- `eth_getLogs`: 특정 조건에 맞는 이벤트 로그 조회

---

## 3. 프로젝트 구조 한눈에 보기

```
vault-ledger/
│
├── chain-indexer-go/          # Go 서비스 — 블록체인 데이터 수집기
│   ├── cmd/
│   │   └── main.go            # 프로그램 시작점 (진입점)
│   ├── internal/
│   │   ├── rpc/
│   │   │   └── client.go      # 블록체인 노드와 통신
│   │   ├── db/
│   │   │   ├── repository.go  # PostgreSQL 데이터 저장/조회
│   │   │   └── repository_test.go  # 테스트 코드
│   │   └── audit/
│   │       ├── audit.go       # 해시 계산, Merkle 트리, 무결성 검증
│   │       └── audit_test.go  # 테스트 코드
│   ├── go.mod                 # Go 의존성 목록 (package.json 같은 것)
│   ├── go.sum                 # 의존성 체크섬 (보안용 잠금 파일)
│   └── Dockerfile             # Go 서비스 컨테이너 빌드 설정
│
├── admin-rails/               # Ruby on Rails 서비스 — 조회 API
│   ├── app/
│   │   ├── controllers/
│   │   │   ├── application_controller.rb  # 모든 컨트롤러의 부모
│   │   │   ├── deposits_controller.rb     # 입금 조회 API
│   │   │   └── audit_controller.rb        # 감사 앵커 API
│   │   └── models/
│   │       ├── application_record.rb      # 모든 모델의 부모
│   │       ├── deposit.rb                 # 입금 데이터 모델
│   │       └── audit_anchor.rb            # 감사 앵커 모델
│   ├── config/
│   │   ├── routes.rb          # URL → 컨트롤러 매핑 테이블
│   │   ├── database.yml       # DB 연결 설정
│   │   ├── application.rb     # Rails 앱 설정
│   │   ├── boot.rb            # Rails 부팅 초기화
│   │   └── environment.rb     # 환경 로드
│   ├── db/migrate/            # DB 스키마 변경 이력
│   │   ├── 20240101000000_create_deposits.rb
│   │   ├── 20240102000000_create_cursors.rb
│   │   └── 20240103000000_create_audit_anchors.rb
│   ├── Gemfile                # Ruby 의존성 목록 (go.mod 같은 것)
│   ├── Gemfile.lock           # 의존성 잠금 파일
│   ├── Rakefile               # 명령어 정의 파일
│   ├── config.ru              # Rack 웹서버 설정
│   └── Dockerfile             # Rails 서비스 컨테이너 빌드 설정
│
├── infra/
│   └── docker-compose.yml     # 세 서비스(Go, Rails, Postgres)를 한번에 실행
│
├── docs/
│   ├── architecture.md        # 시스템 설계 명세
│   └── learning-guide.md      # 이 파일
│
├── .env.sample                # 환경변수 예시 파일
├── .gitignore                 # Git에 올리지 않을 파일 목록
└── README.md                  # 프로젝트 소개
```

---

## 4. 인프라 — Docker와 환경변수

### Docker란?

애플리케이션과 그 실행 환경을 하나의 **컨테이너**에 담는 기술입니다. "내 컴퓨터에서는 됐는데 서버에선 안 돼" 문제를 없애줍니다.

### docker-compose.yml 해설

`infra/docker-compose.yml`은 이 프로젝트의 세 서비스를 동시에 실행하고 연결해주는 **지휘자**입니다.

```yaml
services:
  postgres:                    # 서비스 이름 (다른 서비스에서 이 이름으로 접근)
    image: postgres:15-alpine  # Docker Hub에서 가져올 이미지
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
      POSTGRES_DB: vault_ledger
    ports:
      - "5432:5432"            # "호스트포트:컨테이너포트"
                               # 내 PC의 5432 → 컨테이너 내부 5432로 연결
    volumes:
      - postgres_data:/var/lib/postgresql/data
                               # 컨테이너가 꺼져도 DB 데이터 보존
    healthcheck:               # 다른 서비스가 시작 전, DB가 준비됐는지 확인
      test: ["CMD-SHELL", "pg_isready -U postgres"]

  chain-indexer-go:
    build:
      context: ../chain-indexer-go  # 이 폴더의 Dockerfile로 이미지 빌드
    depends_on:
      postgres:
        condition: service_healthy  # postgres가 완전히 준비된 후에만 시작
    environment:
      DB_DSN: "postgres://postgres:password@postgres:5432/vault_ledger?sslmode=disable"
      #                                       ^^^^^^^^
      #                        서비스 이름 "postgres"가 hostname이 됨
    ports:
      - "2112:2112"            # Prometheus 메트릭 수집용 포트

  admin-rails:
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "3000:3000"            # Rails API 서버 포트
    command: sh -c "bin/rails db:prepare && bin/rails s -b 0.0.0.0"
    #                          ^^^^^^^^^^
    #                  Rails 마이그레이션 실행 후 서버 시작
```

### .env.sample 해설

환경변수는 코드에 직접 적으면 안 되는 **비밀값이나 환경별 설정**을 담습니다.

```bash
RPC_URL=https://sepolia.infura.io/v3/YOUR_KEY
# 블록체인 노드 접속 주소. Infura, Alchemy 같은 서비스에서 발급받습니다.

TARGET_TO=0xYourWalletAddress
# 모니터링할 지갑 주소. 이 주소로 들어오는 입금만 수집합니다.

CHAIN_ID=11155111
# Sepolia 테스트넷의 체인 ID. 메인넷은 1입니다.

POLL_INTERVAL=5s
# 몇 초마다 새 블록을 확인할지 설정합니다.

MAX_BLOCK_RANGE=1000
# 한 번에 조회할 최대 블록 범위. 너무 크면 RPC 서버가 거부합니다.
```

### Dockerfile 해설 (Go 서비스)

```dockerfile
FROM golang:1.21-alpine AS builder   # 1단계: Go 컴파일러가 있는 환경
WORKDIR /app
COPY go.mod ./
RUN go mod download                  # 의존성 먼저 다운로드 (캐시 최적화)
COPY . .
RUN go build -o chain-indexer cmd/main.go  # Go 코드를 바이너리로 컴파일

FROM alpine:3.18                     # 2단계: 최소 실행 환경 (Go 컴파일러 불필요)
WORKDIR /app
COPY --from=builder /app/chain-indexer .  # 컴파일된 바이너리만 복사
CMD ["./chain-indexer"]              # 바이너리 실행
```

이 **멀티스테이지 빌드** 패턴은 최종 이미지 크기를 줄이는 기법입니다. Go 컴파일러 환경(수백 MB)을 최종 이미지에 포함하지 않고, 작은 Alpine Linux(수 MB)에 컴파일된 바이너리만 넣습니다.

---

## 5. Go 서비스 (chain-indexer-go) 완전 해설

### Go 언어 기초 — 이 프로젝트에서 쓰이는 것만

**패키지(Package)**
```go
package main  // 이 파일이 속한 패키지 이름
```
Go의 모든 파일은 패키지에 속합니다. `package main`은 실행 가능한 프로그램의 시작점입니다.

**import**
```go
import (
    "context"  // Go 표준 라이브러리
    "log"

    "chain-indexer-go/internal/db"  // 이 프로젝트 내부 패키지
    "github.com/prometheus/client_golang/prometheus"  // 외부 라이브러리
)
```

**구조체(struct) — 데이터를 묶는 방법**
```go
type DepositEvent struct {
    ChainID      int64    // 체인 ID (정수)
    TxHash       string   // 트랜잭션 해시 (문자열)
    LogIndex     uint64   // 로그 인덱스 (부호 없는 정수)
    AmountRaw    *big.Int // 금액 (포인터: 큰 숫자를 다루기 위해)
}
```
클래스가 없는 Go에서 데이터를 묶는 방법입니다.

**에러 처리 — Go의 특징**
```go
repo, err := db.NewRepository(dbDSN)
if err != nil {
    log.Fatalf("연결 실패: %v", err)
}
```
Go는 예외(Exception)가 없습니다. 함수가 `(결과값, error)`를 반환하면, 항상 에러를 확인해야 합니다. `Fatalf`는 메시지를 출력하고 프로그램을 종료합니다.

**고루틴(goroutine) — 동시 실행**
```go
go func() {
    http.Handle("/metrics", promhttp.Handler())
    log.Fatal(http.ListenAndServe(":2112", nil))
}()
```
`go` 키워드를 붙이면 그 함수가 **백그라운드에서 동시에** 실행됩니다. 메트릭 서버를 띄우면서 메인 폴링 루프도 계속 실행할 수 있는 이유입니다.

**defer — 나중에 실행**
```go
repo, _ := db.NewRepository(dbDSN)
defer repo.Close()  // 이 함수가 끝날 때 자동으로 Close() 호출
```
DB 연결 해제 같은 정리 작업을 잊지 않도록 보장합니다.

---

### go.mod / go.sum 해설

```
chain-indexer-go/go.mod
```

```
module chain-indexer-go   ← 이 모듈의 이름 (import 경로의 기준)

go 1.21                   ← 최소 요구 Go 버전

require (
    github.com/lib/pq v1.10.9
    # PostgreSQL 드라이버. Go의 database/sql과 연결해줍니다.

    github.com/prometheus/client_golang v1.19.0
    # Prometheus 메트릭 수집 라이브러리
)
```

`go.sum`은 각 의존성의 **체크섬(해시)**을 담습니다. 누군가 라이브러리를 악의적으로 교체했을 때 탐지하는 보안 장치입니다. 직접 편집하지 않습니다.

---

### rpc/client.go 해설

블록체인 노드와 통신하는 클라이언트입니다.

```go
// JSON-RPC 요청의 구조
type rpcRequest struct {
    JSONRPC string        `json:"jsonrpc"`  // 항상 "2.0"
    Method  string        `json:"method"`   // 호출할 함수 이름
    Params  []interface{} `json:"params"`   // 인자 목록
    ID      int           `json:"id"`       // 요청-응답 매칭용 번호
}
```

백틱(`` ` ``) 안의 `json:"jsonrpc"`는 **구조체 태그**입니다. JSON으로 직렬화할 때 필드명을 `JSONRPC` 대신 `jsonrpc`(소문자)로 쓰라고 지시합니다. 블록체인 노드가 소문자를 기대하기 때문입니다.

**EthGetLogs의 필터 구조 이해**

```go
filter := map[string]interface{}{
    "fromBlock": "0x13c700",  // 시작 블록 (16진수)
    "toBlock":   "0x13c7e8",  // 끝 블록 (16진수)
    "topics": []interface{}{
        "0xddf252...",  // Topic[0]: Transfer 이벤트만
        nil,            // Topic[1]: from 주소 무관
        "0x000...abc",  // Topic[2]: to 주소 = 내 지갑
    },
}
```

왜 주소 앞에 0이 많이 붙나요? 이더리움 주소는 20바이트(40 hex)지만, Topic은 32바이트(64 hex) 고정이라서 앞에 0을 채웁니다. 이것이 `paddedTarget`입니다:

```go
// cmd/main.go
cleanAddress := strings.TrimPrefix(targetTo, "0x")
paddedTarget := "0x000000000000000000000000" + cleanAddress
//                ^^^^^^^^^^^^^^^^^^^^^^^^^ 24자 = 12바이트 패딩
```

---

### db/repository.go 해설

PostgreSQL과 대화하는 계층입니다.

**Repository 패턴**
```go
type Repository struct {
    db *sql.DB  // 소문자로 시작 = 패키지 외부에서 접근 불가 (캡슐화)
}
```
데이터베이스 연결을 구조체 안에 숨기고, 메서드를 통해서만 접근하게 합니다.

**멱등 삽입 (ON CONFLICT DO NOTHING)**
```go
query := `
    INSERT INTO deposits (...) VALUES (...)
    ON CONFLICT (chain_id, tx_hash, log_index) DO NOTHING
`
```
같은 이벤트를 100번 넣어도 1개만 저장됩니다. 네트워크 오류로 같은 블록 범위를 재처리해도 데이터가 중복되지 않습니다. 이것이 이 시스템의 핵심 안전장치입니다.

**RunMigrations**
```go
func (r *Repository) RunMigrations(ctx context.Context) error {
    queries := []string{
        `CREATE TABLE IF NOT EXISTS deposits (...)`,  // IF NOT EXISTS = 이미 있으면 무시
        `CREATE TABLE IF NOT EXISTS cursors (...)`,
        `CREATE TABLE IF NOT EXISTS audit_anchors (...)`,
    }
    for _, q := range queries {
        r.db.ExecContext(ctx, q)
    }
}
```
Rails의 마이그레이션 파일과 같은 역할이지만, Go는 직접 SQL을 실행합니다. 프로그램 시작 시 자동으로 테이블을 만들기 때문에 별도의 DB 세팅 없이 바로 실행됩니다.

**Context란?**
```go
ctx, cancel := context.WithCancel(context.Background())
defer cancel()
```
Go에서 작업의 **취소·타임아웃**을 전달하는 객체입니다. `cancel()`을 호출하면 이 ctx를 사용하는 모든 DB 쿼리, RPC 호출이 중단 신호를 받습니다. graceful shutdown 구현에 사용됩니다.

---

### cmd/main.go 해설

**프로그램의 전체 흐름**

```
시작
 │
 ├─ flag.Parse()          ← CLI 플래그 파싱 (--replay, --verify-audit 등)
 ├─ 환경변수 읽기
 ├─ DB 연결
 ├─ RunMigrations()       ← 테이블 자동 생성
 ├─ SIGINT/SIGTERM 시그널 감지 설정 (Ctrl+C 처리)
 │
 ├─ [모드 분기]
 │   ├─ --replay 모드     → processBlockRange() 후 종료
 │   ├─ --verify-audit    → runVerifyAudit() 후 종료
 │   ├─ --create-anchor   → runCreateAnchor() 후 종료
 │   └─ (없음)            → 폴링 루프 진입
 │
 └─ [폴링 루프]
     ├─ 5초마다 깨어나기
     ├─ eth_blockNumber 호출 → 최신 블록 확인
     ├─ processBlockRange() → 새 블록들 처리
     └─ UpdateCursor()      → 처리된 위치 저장
```

**Graceful Shutdown**
```go
sigCh := make(chan os.Signal, 1)
signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
go func() {
    sig := <-sigCh          // Ctrl+C 또는 Docker stop 신호 대기
    log.Printf("Received signal %v, shutting down...", sig)
    cancel()                // context 취소 → 모든 작업 중단 신호
}()
```
서버를 갑자기 끄면 처리 중이던 블록이 반만 처리될 수 있습니다. 이 코드는 신호를 받으면 현재 청크를 완료한 뒤 안전하게 종료합니다.

**Prometheus 메트릭**
```go
var (
    lastProcessedBlockMetric = prometheus.NewGauge(...)   // 단순 숫자값 (증감 가능)
    eventsSavedTotalMetric   = prometheus.NewCounter(...) // 누적 카운터 (증가만)
    rpcLatencyMetric         = prometheus.NewHistogramVec(...) // 분포 측정
)
```

- **Gauge**: 현재 온도계처럼 현재값을 나타냄 → 처리된 마지막 블록 번호
- **Counter**: 적산 전력계처럼 계속 증가 → 저장된 이벤트 수
- **Histogram**: 응답속도 분포 측정 → RPC 호출이 0.1초, 0.5초, 1초 대에 얼마나 있는지

`:2112/metrics`에 접속하면 Prometheus 서버가 이 값들을 읽어서 Grafana 같은 대시보드에 시각화합니다.

---

### audit/audit.go 해설

이 파일은 **암호학적 무결성 증명**을 담당합니다. 자세한 설명은 [10. 핵심 알고리즘 해설](#10-핵심-알고리즘-해설--merkle-tree--해시-체인)을 참고하세요.

```go
// 이벤트 하나를 고유한 지문(해시)으로 변환
func EventHash(e db.DepositEvent) string {
    data := fmt.Sprintf("%d|%s|%d|%d|%s|%s|%s|%s",
        e.ChainID, e.TxHash, e.LogIndex, e.BlockNumber,
        e.FromAddress, e.ToAddress, e.TokenAddress, e.AmountRaw.String(),
    )
    h := sha256.Sum256([]byte(data))
    return hex.EncodeToString(h[:])
}
```

SHA-256은 어떤 입력이든 256비트(64자 16진수)의 고정 길이 출력을 만듭니다. 입력이 1비트라도 바뀌면 출력이 완전히 달라집니다. 이 성질을 이용해 데이터 변조를 탐지합니다.

---

## 6. Ruby 서비스 (admin-rails) 완전 해설

### Ruby on Rails 기초

**MVC 패턴**

Rails는 코드를 세 역할로 분리합니다:

```
요청 →  Router(routes.rb)
         │
         ↓
      Controller (*.rb)   ← 요청 처리, 로직 실행
         │
         ↓
       Model (*.rb)       ← 데이터베이스와 대화
         │
         ↓
      (View)              ← HTML 생성 (API 모드라 이 프로젝트에선 없음)
         │
         ↓
      응답 (JSON)
```

### config/routes.rb 해설

```ruby
Rails.application.routes.draw do
  get '/deposits',      to: 'deposits#index'
  # "GET /deposits 요청이 오면 DepositsController의 index 메서드를 실행해"

  get '/health',        to: 'deposits#health'
  # DepositsController의 health 메서드로

  get '/audit/anchors', to: 'audit#anchors'
  # AuditController의 anchors 메서드로

  get '/audit/verify',  to: 'audit#verify'
  # AuditController의 verify 메서드로
end
```

**컨트롤러명 규칙**: `deposits#index`에서 `deposits`는 `DepositsController`를 의미합니다. Rails가 자동으로 `Deposits` + `Controller`로 변환합니다.

### app/controllers/deposits_controller.rb 해설

```ruby
class DepositsController < ApplicationController
  # ApplicationController를 상속: 공통 기능(인증 등) 자동 포함

  def index
    deposits = Deposit.order(block_number: :desc, log_index: :desc)
    # Deposit 모델로 DB에서 조회. SQL: SELECT * FROM deposits ORDER BY block_number DESC

    if params[:to_address].present?
      deposits = deposits.where(to_address: params[:to_address])
      # GET /deposits?to_address=0x... 처럼 쿼리스트링으로 필터링
    end

    limit = params[:limit].present? ? params[:limit].to_i : 50
    # limit 파라미터가 없으면 기본값 50

    render json: deposits
    # 결과를 JSON으로 응답
  end

  def health
    ActiveRecord::Base.connection.execute("SELECT 1")
    # DB에 쿼리 날려서 연결 확인
    render json: { status: 'ok' }, status: :ok
  rescue => e
    # 에러 발생 시 503 응답
    render json: { status: 'error', message: e.message }, status: :service_unavailable
  end
end
```

### app/models/deposit.rb 해설

```ruby
class Deposit < ApplicationRecord
  # ApplicationRecord 상속 → 자동으로 deposits 테이블과 연결됨
  # Rails 규칙: 모델명 Deposit → 테이블명 deposits (복수형, 소문자)

  validates :chain_id, :tx_hash, presence: true
  # 이 필드들은 반드시 있어야 저장됨 (DB 저장 전 검증)

  validates :tx_hash, uniqueness: { scope: [:chain_id, :log_index] }
  # (chain_id, tx_hash, log_index) 조합이 유니크해야 함

  def amount_decimal(decimals = 18)
    amount_raw / (10.0 ** decimals)
    # ERC-20은 소수점을 정수로 저장함. 18자리 소수점이 기본값.
    # 1 ETH = 1_000_000_000_000_000_000 (10^18) wei
  end
end
```

### db/migrate/ 해설 — Rails 마이그레이션

마이그레이션은 DB 스키마 변경의 **이력 관리** 시스템입니다. 파일명 앞의 타임스탬프(`20240101000000`)로 실행 순서를 결정합니다.

```ruby
# 20240101000000_create_deposits.rb
class CreateDeposits < ActiveRecord::Migration[7.0]
  def change
    create_table :deposits do |t|
      t.bigint  :chain_id,      null: false
      t.string  :tx_hash,       null: false
      t.bigint  :log_index,     null: false
      t.bigint  :block_number,  null: false
      t.numeric :amount_raw, precision: 78, scale: 0, null: false
      # precision: 78 → 최대 78자리 숫자
      # ERC-20 최대값은 2^256 ≈ 10^77 이므로 78자리면 충분

      t.timestamps  # created_at, updated_at 자동 추가
    end

    add_index :deposits, [:chain_id, :tx_hash, :log_index], unique: true
    # 복합 유니크 인덱스: 중복 저장 방지 + 조회 속도 향상
  end
end
```

**Go의 RunMigrations vs Rails 마이그레이션의 차이점**

| 항목 | Go (RunMigrations) | Rails (migrate/) |
|------|-------------------|-----------------|
| 방식 | `IF NOT EXISTS` SQL 직접 실행 | 마이그레이션 파일 + schema_migrations 테이블 |
| 이력 관리 | 없음 (항상 재실행 가능) | 있음 (실행된 것은 다시 실행 안 함) |
| 롤백 | 지원 안 함 | `rake db:rollback`으로 되돌리기 가능 |

왜 두 곳에 마이그레이션이 있나요? Go 서비스가 자체적으로 테이블을 만들기 때문에 Rails 마이그레이션이 없어도 테이블은 존재합니다. Rails의 마이그레이션은 Rails 개발자 도구(`db:schema:dump` 등)와의 연동을 위해 **선언**만 해두는 것입니다.

### config/ 파일들 해설

**application.rb** — Rails 앱의 핵심 설정
```ruby
config.api_only = true  # View 레이어 없이 JSON API만 사용
```

**boot.rb** — Bundler(의존성 관리자) 초기화
```ruby
require 'bundler/setup'  # Gemfile.lock의 버전으로 의존성 로드
```

**environment.rb** — 환경 로드
```ruby
Rails.application.initialize!  # 앱 초기화 실행
```

**config.ru** — Rack 웹서버 설정 파일
```ruby
run Rails.application  # Rack 인터페이스에 Rails 앱 연결
```
Puma 같은 웹서버가 이 파일을 읽어서 Rails 앱을 실행합니다.

**Rakefile** — rake 명령어 등록
```ruby
require 'rails/tasks'  # rails db:migrate, rails routes 같은 명령어 등록
```

### Gemfile / Gemfile.lock 해설

```ruby
# Gemfile
gem 'rails', '~> 7.0.8'
# ~> 7.0.8 의미: 7.0.8 이상, 7.1.0 미만 (패치 버전만 자동 업그레이드)

gem 'pg', '~> 1.1'
# PostgreSQL 어댑터 (Go의 github.com/lib/pq와 같은 역할)

gem 'puma', '~> 5.0'
# 웹서버 (Go의 net/http 내장 서버에 해당)

gem 'bootsnap', require: false
# Rails 시작 속도 최적화 (파일 캐싱)
```

`Gemfile.lock`은 `go.sum`처럼 정확한 버전을 고정합니다. 팀원 모두가 동일한 버전을 사용하도록 보장합니다.

---

## 7. 데이터베이스 — 테이블 설계와 이유

### deposits 테이블 — 핵심 데이터

```sql
CREATE TABLE deposits (
    id           BIGSERIAL PRIMARY KEY,
    chain_id     BIGINT NOT NULL,         -- Sepolia: 11155111
    tx_hash      TEXT NOT NULL,           -- 0x4f8a...
    log_index    BIGINT NOT NULL,         -- 같은 tx에 여러 Transfer가 있을 때 구분
    block_number BIGINT NOT NULL,         -- 어떤 블록에서 발생했는지
    from_address TEXT NOT NULL,           -- 보낸 주소
    to_address   TEXT NOT NULL,           -- 받은 주소 (TARGET_TO)
    token_address TEXT NOT NULL,          -- 어떤 ERC-20 토큰인지
    amount_raw   NUMERIC(78, 0) NOT NULL, -- 토큰 최솟값 단위 (wei 개념)
    created_at   TIMESTAMP NOT NULL,
    updated_at   TIMESTAMP NOT NULL
);

-- 왜 (chain_id, tx_hash, log_index) 유니크 인덱스인가?
-- tx_hash만으로는 부족: 하나의 트랜잭션에 Transfer가 여러 개일 수 있음
-- chain_id 포함: 같은 tx_hash가 다른 체인에도 존재할 수 있음
CREATE UNIQUE INDEX ON deposits (chain_id, tx_hash, log_index);
```

**amount_raw가 NUMERIC(78, 0)인 이유**

ERC-20 토큰 금액은 소수점 없이 최솟값 단위로 저장됩니다. 1 USDC(소수점 6자리)는 실제로 `1_000_000`으로 저장됩니다. 1 ETH(소수점 18자리)는 `1_000_000_000_000_000_000`입니다. ERC-20의 이론적 최대값은 2^256 ≈ 7.9 × 10^76으로 78자리가 필요합니다. `float`이나 `int64`로는 정밀도가 손실되기 때문에 `NUMERIC`을 씁니다.

### cursors 테이블 — 재시작 위치 기억

```sql
CREATE TABLE cursors (
    id                   BIGSERIAL PRIMARY KEY,
    chain_id             BIGINT NOT NULL UNIQUE,  -- 체인당 1개 커서
    last_processed_block BIGINT NOT NULL DEFAULT 0,
    updated_at           TIMESTAMP NOT NULL
);
```

**왜 필요한가?** Go 서비스가 크래시하면, 마지막으로 처리한 블록부터 다시 시작해야 합니다. 처음엔 `MAX(block_number) FROM deposits`로 추정했지만, 특정 블록에 이벤트가 없으면 그 블록이 처리됐는지 알 수 없습니다. `cursors` 테이블은 이벤트 유무와 관계없이 처리된 블록 위치를 별도로 기록합니다.

### audit_anchors 테이블 — 무결성 증명서

```sql
CREATE TABLE audit_anchors (
    id              BIGSERIAL PRIMARY KEY,
    chain_id        BIGINT NOT NULL,
    anchor_date     DATE NOT NULL,        -- 하루 단위로 생성
    from_block      BIGINT NOT NULL,      -- 그날의 첫 블록
    to_block        BIGINT NOT NULL,      -- 그날의 마지막 블록
    event_count     INTEGER NOT NULL,     -- 그날의 이벤트 수
    merkle_root     TEXT NOT NULL,        -- 모든 이벤트의 Merkle 루트 해시
    prev_anchor_hash TEXT NOT NULL,       -- 전날 앵커의 해시 (체인 연결)
    anchor_hash     TEXT NOT NULL,        -- 이 앵커 전체의 해시
    created_at      TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX ON audit_anchors (chain_id, anchor_date);
-- 날짜당 1개만 허용 = append-only (수정 불가 설계)
```

---

## 8. v0 → v1 → v2 진화 스토리

이 프로젝트는 세 단계로 발전했습니다. 각 버전이 **어떤 문제를 해결했는지** 이해하면 설계 의도가 보입니다.

### v0: 일단 동작하게 만들기

**목표**: 블록체인에서 Transfer 이벤트를 읽어서 DB에 저장

**핵심 기능**:
- `eth_getLogs`로 폴링
- `ON CONFLICT DO NOTHING`으로 멱등성 보장
- Prometheus 기본 메트릭 3개

**문제점**:
- 크래시 후 재시작 시 어디서부터 재개할지 불명확
- 성능 관측 불가 (RPC 지연, 처리 지연 측정 없음)
- 실수로 같은 블록을 다시 처리할 방법이 없음

### v1: 운영 가능하게 만들기

**추가된 것**:
```
cursors 테이블        → 크래시 복구 위치 정확히 기억
--replay 모드         → 특정 블록 범위 재처리
SIGTERM 처리          → 컨테이너 재시작 시 안전하게 종료
indexer_lag_blocks    → 얼마나 뒤처져있는지 모니터링
rpc_latency_seconds   → RPC 병목 탐지
db_upsert_conflicts_total → 중복 처리 빈도 측정
```

**해결된 문제**:
- Kubernetes에서 Pod를 재시작해도 안전
- "RPC가 느린데 어디서 병목인지 모르겠어" → 메트릭으로 즉시 확인

### v2: 감사 가능하게 만들기

**추가된 것**:
```
audit_anchors 테이블   → 일별 암호학적 무결성 기록
internal/audit/       → SHA-256, Merkle 트리, 해시 체인
--create-anchor       → 특정 날짜 앵커 생성
--verify-audit        → 전체 무결성 검증
/audit/anchors API    → 앵커 목록 조회
/audit/verify API     → 특정 날짜 일관성 확인
```

**해결된 문제**:
- "DB 관리자가 입금 데이터를 몰래 바꿨는지 어떻게 알아?" → `--verify-audit`으로 탐지 가능

---

## 9. 데이터가 흐르는 전체 경로 (end-to-end)

실제 토큰 전송 하나가 이 시스템에서 어떻게 처리되는지 추적합니다.

```
1. 블록체인에서 발생
   Alice가 Bob(TARGET_TO)에게 100 USDC 전송
   → Sepolia 블록 #7,123,456에 Transfer 이벤트 기록

2. chain-indexer-go 폴링 (5초마다)
   client.EthBlockNumber() → 7,123,460 (최신)
   GetCursor() → 7,123,455 (마지막 처리)
   "5개 블록 처리해야 함"

3. processBlockRange() 실행
   EthGetLogs(7123456, 7123456, target=Bob) 호출
   → [{
       address: "0xusdc_contract",
       topics: ["0xddf252...", "0x000...alice", "0x000...bob"],
       data: "0x5f5e100",  ← 100 USDC in hex (6자리 소수점: 100_000_000)
       blockNumber: "0x6cc9c8",
       transactionHash: "0xabc...",
       logIndex: "0x0"
     }]

4. 파싱
   blockNum = parseHexUint("0x6cc9c8") = 7,123,400
   fromAddr = "0x" + topics[1][26:] = "0xalice_address"
   toAddr   = "0x" + topics[2][26:] = "0xbob_address"
   amount   = new(big.Int).SetString("5f5e100", 16) = 100_000_000

5. DB 저장
   repo.SaveDeposit(DepositEvent{
     ChainID: 11155111, TxHash: "0xabc...", LogIndex: 0,
     BlockNumber: 7123456, FromAddress: "0xalice...", ToAddress: "0xbob...",
     TokenAddress: "0xusdc_contract", AmountRaw: 100_000_000
   })
   → INSERT ... ON CONFLICT DO NOTHING
   → 1 row inserted, saved=true

6. 커서 업데이트
   UpdateCursor(chainID=11155111, block=7123456)
   → cursors 테이블 갱신

7. 메트릭 업데이트
   eventsSavedTotalMetric.Inc()   → events_saved_total +1
   lastProcessedBlockMetric.Set(7123456)
   indexerLagBlocksMetric.Set(4)  → 아직 7123457~7123460 처리 안 됨

8. 관리자가 API 조회
   GET http://localhost:3000/deposits?to_address=0xbob...

   DepositsController#index 실행:
   Deposit.where(to_address: "0xbob...").order(block_number: :desc)
   → SELECT * FROM deposits WHERE to_address='0xbob...' ORDER BY block_number DESC

   응답:
   [{
     "id": 1,
     "chain_id": 11155111,
     "tx_hash": "0xabc...",
     "block_number": 7123456,
     "from_address": "0xalice...",
     "to_address": "0xbob...",
     "token_address": "0xusdc_contract",
     "amount_raw": "100000000",
     "created_at": "2024-01-15T10:30:00Z"
   }]
```

---

## 10. 핵심 알고리즘 해설 — Merkle Tree & 해시 체인

### SHA-256이란?

어떤 데이터든 256비트(64자 16진수)의 **지문**으로 변환하는 함수입니다.

```
"hello" → SHA-256 → "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
"Hello" → SHA-256 → "185f8db32921bd46d35f5ef1dc77f3ac2d4e7a64b4b02d1d4e0e4e22b4cde3fe"
```

한 글자만 달라져도 결과가 완전히 다릅니다. 역방향 계산은 불가능합니다(해시 → 원본 복원 불가).

### Merkle Tree 작동 원리

4개의 입금 이벤트가 있다고 가정합니다:

```
이벤트:  E1          E2          E3          E4
해시:    H(E1)       H(E2)       H(E3)       H(E4)
            \         /              \         /
             H(E1+E2)                H(E3+E4)
                     \              /
                      H(E1+E2+E3+E4)  ← Merkle Root
```

**왜 유용한가?**

Merkle Root 하나만 저장해도, 나중에 같은 이벤트들로 루트를 다시 계산해서 비교할 수 있습니다. E2의 금액이 하나라도 바뀌면 루트가 완전히 달라집니다.

**홀수 개의 이벤트 처리**
```go
// audit.go
} else {
    // Odd: duplicate the last leaf
    combined := leaves[i] + leaves[i]  // 마지막 노드를 자신과 합침
}
```

3개의 이벤트:
```
H(E1)   H(E2)   H(E3)   H(E3) ← 복제
   \     /          \     /
  H(E1+E2)         H(E3+E3)
         \         /
         Merkle Root
```

### 앵커 해시 체인

Merkle Root만으로는 "1월 1일 앵커가 맞는지"는 알 수 있지만, "앵커들이 순서대로 연결돼있는지"는 알 수 없습니다. 앵커 해시 체인이 이것을 해결합니다.

```
Day 1 앵커:
  prev_anchor_hash = ""  (첫 번째)
  merkle_root      = MR1
  anchor_hash      = SHA-256("" | MR1 | "2024-01-01" | 11155111)

Day 2 앵커:
  prev_anchor_hash = Day1.anchor_hash  ← 체인 연결!
  merkle_root      = MR2
  anchor_hash      = SHA-256(Day1.anchor_hash | MR2 | "2024-01-02" | 11155111)

Day 3 앵커:
  prev_anchor_hash = Day2.anchor_hash
  ...
```

Day 1 데이터를 바꾸면 Day 1의 anchor_hash가 바뀌고, 이를 참조하는 Day 2의 prev_anchor_hash와 맞지 않게 됩니다. 결국 연쇄적으로 모든 이후 앵커가 불일치해서 변조가 탐지됩니다. 이것이 블록체인의 해시 체인 원리와 동일합니다.

### --verify-audit 동작 과정

```go
// cmd/main.go → runVerifyAudit()
func runVerifyAudit(...) {
    anchors := repo.GetAuditAnchors()  // DB에서 모든 앵커 가져오기

    for i, anchor := range anchors {
        events := repo.GetDepositsByDateRange(anchor.AnchorDate)  // 해당 날짜 이벤트

        // 1. Merkle Root 재계산
        recomputedRoot := audit.BuildMerkleRoot(events)
        if recomputedRoot != anchor.MerkleRoot {
            // 이벤트 데이터가 변조됨!
        }

        // 2. Anchor Hash 재계산
        recomputedHash := audit.ComputeAnchorHash(anchor.PrevAnchorHash, ...)
        if recomputedHash != anchor.AnchorHash {
            // 앵커 자체가 변조됨!
        }

        // 3. 체인 연결 확인
        if anchor.PrevAnchorHash != anchors[i-1].AnchorHash {
            // 앵커 순서가 끊겼음!
        }
    }
}
```

---

## 마치며 — 이 프로젝트가 가르쳐주는 것들

| 개념 | 이 프로젝트에서 배우는 것 |
|------|--------------------------|
| **멱등성** | 같은 작업을 N번 해도 결과가 동일해야 함 (`ON CONFLICT DO NOTHING`) |
| **폴링 vs 이벤트** | 블록체인은 push가 없으니 직접 물어봐야 함 |
| **관심사 분리** | Go(수집) + Rails(조회) + Postgres(저장) 역할 분담 |
| **Graceful Shutdown** | 갑자기 꺼지면 데이터가 깨질 수 있다 |
| **암호학적 무결성** | 신뢰할 수 없는 환경에서 데이터 변조를 수학으로 탐지 |
| **점진적 개선** | v0에서 동작시키고, v1에서 견고하게, v2에서 신뢰 가능하게 |
