---
title: "[네트워킹]애플리케이션 계층(Application Layer) - HTTP, DNS, 이메일"
date: 2026-02-19 12:00:00 +0900
categories: [CS]
tags: [networking, http, dns, smtp, application-layer]
---

# 2.1 네트워크 애플리케이션의 원리

## 애플리케이션 아키텍처

- 클라이언트-서버(Client-Server): 항상 켜져 있는 호스트(서버)가 있고, 클라이언트들이 서버에 요청을 보낸다. 서버는 고정 IP를 가지며, 데이터 센터에 위치하여 확장성을 가짐.
- P2P(Peer-to-Peer): 항상 켜져 있는 서버에 최소한으로 의존하며, 피어(Peer)라 불리는 간헐적으로 연결된 호스트들이 서로 직접 통신한다. 피어들이 자원을 요청함과 동시에 제공하므로, 자가 확장성(Self-scalability)가 뛰어남.

## 프로세스 간 통신

- 서로 다른 호스트에서 실행되는 프로세스들은 메시지(Message)를 교환하며 통신한다.
- 소켓(Socket): 애플리케이션과 네트워크 사이의 소프트웨어 인터페이스, 프로세스는 소켓을 통해 메시지를 주고받을 수 있다.
    - application layer와 transport layer사이의 인터페이스로서 Application Programming Interface(API)라고도 볼 수 있음.
    - 이 소켓 인터페이스의 존재로 인해 개발자는 손쉽게 데이터를 송/수신할 수 있음.
        - transport protocol 정하기
        - 필요에 따라 transport-layer의 parameter 수정

[![seukeulinsyas-2026-02-17-21-25-17.png](https://i.postimg.cc/Kv84p337/seukeulinsyas-2026-02-17-21-25-17.png)](https://postimg.cc/PN0tPx4N)

## 전송 계층(transport layer)의 프로토콜이 애플리케이션에 제공하는 서비스

- 신뢰적 데이터 전송(Reliable Data Transfer): 손실 없이 프로세스 간에 데이터 전송을 보장.
    - 특정 애플리케이션(loss-tolerant applications)에서는 일부 데이터 손실은 감수할 수 있음
    → audio/video 등의 멀티미디어 애플리케이션
- 처리율(Throughput): 일정 수준 이상의 대역폭 보장
    - 예를 들어, 인터넷 전화앱은 음성을 32kbps로 encode한다면, 32kbps의 처리율을 보장할 수 있어야 함.
    - 음성/영상 → 일정량의 처리율을 요구사항으로 가진 앱 → bandwidth-sensitive applications
    - 메일, 파일 전송, 웹 → 상대적으로 처리율에 민감하지 않은 앱 → elastic applications
- 시간(Timing): 낮은 지연 시간 보장
    - transport protocol은 시간 보장을 제공할 수 있음
    - 예를 들어, 송신자가 소켓으로 내보내는 모든 비트가 수신자의 소켓에 100ms내에 도착하게 할 수 있다.
- 보안(Securiy): 암호화 및 무결성 보장
    - transport 프로토콜을 통해 송신 호스트에서 모든 데이터를 암호화할 수 있고, 수신 호스트에서 모두 해독할 수 있다.
    - 보통 TCP를 애플리케이션 계층에서 강화하여 TLS로 보안 서비스를 제공함

| Application | Application-Layer Protocol | Underlying Transport Protocol |
| --- | --- | --- |
| Electronic mail | SMTP [RFC 5321] | TCP |
| Remote terminal access | Telnet [RFC 854] | TCP |
| Web | HTTP 1.1 [RFC 7230] | TCP |
| File transfer | FTP [RFC 959] | TCP |
| Streaming multimedia | HTTP(e.g., YouTube), DASH | TCP |
| Internet telephony | SIP [RFC 3261], RTP[RFC 3550], or proprietary(e.g., Skype) | UDP or TCP |

---

# 2.2 웹과 HTTP

## HTTP(HyperText Transfer Protocol)

https://datatracker.ietf.org/doc/html/rfc2616

웹의 애플리케이션 계층 프로토콜!

- 특징: 비상태(stateless) 프로토콜로, 서버는 클라이언트의 과거 요청 정보를 저장하지 않는다. TCP를 전송 프로토콜로 사용.
- 연결 방식:
    - Non-persistent 연결: 각 요청/응답 쌍마다 별도의 TCP연결을 맺고 끊음 (HTTP/1.0의 기본 방식).
    - Persistent 연결: 단일 TCP 연결을 통해 여러 객체를 전송 (HTTP/1.1의 기본 방식).

## HTTP 메시지 포멧

### HTTP 요청 메시지

RFC는 HTTP 메시지 포멧을 정의한다.

[![seukeulinsyas-2026-02-17-22-16-48.png](https://i.postimg.cc/JhZhHbS8/seukeulinsyas-2026-02-17-22-16-48.png)](https://postimg.cc/gwcpf6Yt)

- HTTP 요청 메시지 예시:
    
    ```java
    GET /somedir/page.html HTTP/1.1
    Host: www.someschool.edu
    Connection: close
    User-agent: Mozilla/5.0
    Accept-language: fr
    ```
    

- 특징
    1. ASCII텍스트로 쓰여 있어 사람들이 읽을 수 있음.
    2. 메시지가 다섯줄로 되어 있고, 각 줄은 CR(carriage return)과 LF(line feed)로 구별된다. 마지막 줄에 이어서 CR과 LF가 따른다.

HTTP 요청 메시지의 첫 줄은 요청 라인이라 부르고, 이후의 줄들은 헤더 라인이라고 부른다.

### 요청 라인(Request line)

요청 라인은 3개의 필드, `method` , `URL` , `HTTP version` 을 갖는다.

method필드에는 `GET` , `POST` , `HEAD` , `PUT` ,`DELETE` 등의 여러 가지 값을 가질 수 있다.

### 헤더 라인(Header lines)

1. Host
    1. 객체가 존재하는 호스트를 명시
    2. 이미 호스트까지 TCP연결이 맺어져 있어 불필요하다고 생각될 수 있지만, 웹 프록시 캐시에서 필요로 한다.
2. Connection: 서버에게 원하는 연결 방식 전달(지속 연결 / 비지속 연결)
3. User-agent: 서버에게 요청을 하는 브라우저 타입을 명시
4. Accept-language: 사용자가 객체의 어떤 언어 버전을 원하고 있는지 나타냄

### entity body

- `GET`일 때는 비어있고, `POST`일 때 사용된다.
- `POST`메시지로 사용자는 서버에 웹 페이지를 요청하고 있으나, 웹 페이지의 특정 내용은 사용자가 폼 필드에 무엇을 입력하는가에 달려 있다.
    - 폼으로 생성한 요구가 반드시 `POST`일 필요는 없다. 대신에 흔히 요청된 URL의 입력 데이터를 전송한다.
- `HEAD` 방식은 `GET`과 유사하다.
    - 서버가 `HEAD`방식을 가진 요청을 받으면 HTTP메시지로 응답하는데, 요청 객체는 보내지 않는다. 흔히 디버깅을 위해 사용
- `PUT` 방식은 웹 서버에 업로드할 객체를 필요로하는 애플리케이션에 의해 사용된다.
- `DELETE` 방식은 사용자 또는 애플리케이션이 웹 서버에 있는 객체를 지우는 것을 허용한다.

---

### HTTP 응답 메시지

[![seukeulinsyas-2026-02-19-20-29-27.png](https://i.postimg.cc/v83Zn820/seukeulinsyas-2026-02-19-20-29-27.png)](https://postimg.cc/kDRC3CmS)

- HTTP 응답 메시지 예시
    
    ```java
    HTTP/1.1 200 OK
    Connection: close
    Date: Tue, 18 Aug 2015 15:44:04 GMT
    Server: Apache/2.2.3 (CentOS)
    Last-Modified: Tue, 18 Aug 2015 15:11:03 GMT
    Content-Length: 6821
    Content-Type: text/html
    (data data data data data ...)
    ```
    

### 상태 라인(status line)과 상태 코드(status code) & phrase

- 200 OK: 요청이 성공했고, 정보가 응답으로 보내졌음.
- 301 Moved Permanently: 요청 객체가 영구적으로 이동되었음. 이때, 새로운 URL은 응답 메시지의 Location 헤더에 나와 있다.
- 400 Bad Request: 서버가 요청을 이해할 수 없음.
- 404 Not Found: 요청한 문서가 서버에 존재하지 않음
- 505 HTTP Version Not Supported: 요청 HTTP프로토콜 버전을 서버가 지원하지 않음.

### 헤더 라인(Header lines)

HTTP명세서는 많은 헤더라인을 정의하고 있고, 위의 예시는 그중 일부

브라우저는 브라우저 타입과 여러 설정, 캐싱하고 있는지에 따라 헤더 라인을 동적으로 생성하고 웹 서버도 비슷하다.

---

## 사용자-서버 간 상호작용: 쿠키(Cookies)

[![seukeulinsyas-2026-02-19-20-35-12.png](https://i.postimg.cc/Bv9S3jbw/seukeulinsyas-2026-02-19-20-35-12.png)](https://postimg.cc/bZgcHNQQ)

HTTP서버는 기본적으로 상태를 유지하지 않는다.

그러나 서버가 사용자 접속을 제한하거나 사용자에 따라 콘텐츠를 제공하기 원할 때, 사용자를 확인하는 것이 바람직 할때가 있다. 이때 쿠키(Cookie)를 해당 요구사항을 충족한다.

https://datatracker.ietf.org/doc/html/rfc6265

그림은 쿠키가 어떻게 동작하는지 설명한다.

(1) 서버가 유저를 식별할 번호를 만들고, 백엔드 DB에 엔트리를 만든 후, HTTP 응답 헤더에 `Set-cookie: 1678` 를 담아 보냄

(2) 유저(브라우저)는 해당 쿠키 파일을 가지고 있다가, 유저의 요청이 발생하면 헤더에 `cookie: 1678` 를 담아 서버에 HTTP요청 전송, 서버에서는 특정 유저를 식별

(3) 특정 유저가 식별되면 백엔드 DB에서 해당 유저에 맞는(Cookie-specific action) 정보를 보여줌

## 웹 캐싱

https://datatracker.ietf.org/doc/html/rfc7234

웹 캐시(Web cache) - proxy server로도 불림 -는 기점 웹 서버를 대신하여 HTTP 요구를 충족시키는 개체.

웹 캐시는 자체적인 저장 디스크를 보유해, 최근 호출된 객체의 사본을 저장 및 보존한다.

### 프록시 서버 동작 과정

[![seukeulinsyas-2026-02-19-20-49-04.png](https://i.postimg.cc/LXv2jvDF/seukeulinsyas-2026-02-19-20-49-04.png)](https://postimg.cc/34ysTXzt)

(1) 브라우저가 웹 캐시(Proxy server)와 TCP연결을 생성하고 HTTP 요청을 보낸다.

(2) 웹 캐시는 해당 요청에 대한 객체 사본이 저장되어 있는지 확인하고, 있다면 바로 응답한다.

(3) 만약 사본을 저장하고 있지 않다면, 기점 서버(Origin server)로 연결을 설정하고, 필요한 정보를 HTTP요청/응답으로 주고받는다.

(4) 웹 캐시가 원본 객체를 수신할때 해당 사본을 로컬 스토리지에 저장, 사본을 브라우저(유저)에게 HTTP응답으로 보내준다.

일반적으로 웹 캐시는 ISP가 구성하고 설치한다.

웹 캐시를 사용함으로서 얻을 수 있는 효과는

1. 클라이언트 요구에 대한 응답 시간을 줄일 수 있음
특히, 클라이언트와 Origin Server의 병목이 두 네트워크망 사이의 연결 대역폭 때문인 경우, Proxy Server가 병목지점(Bottleneck) 바깥에 위치하여 응답시간을 단축시킬 수 있음.
2. Origin Server에 대한 트래픽을 줄일 수 있음
웹 캐시를 클라이언트의 access link 안쪽의 고속망을 공유하는 하나의 네트워크 망에 포함시켜 위치시켜, 실질 웹 트래픽 감소를 노릴 수 있음.

[![seukeulinsyas-2026-02-19-21-02-28.png](https://i.postimg.cc/VLJmbqCv/seukeulinsyas-2026-02-19-21-02-28.png)](https://postimg.cc/MvJhCjtJ)

[![seukeulinsyas-2026-02-19-21-02-57.png](https://i.postimg.cc/7LkkcjQ5/seukeulinsyas-2026-02-19-21-02-57.png)](https://postimg.cc/gxNQLtpp)

---

## HTTP/2

https://datatracker.ietf.org/doc/html/rfc7540

HTTP/2는 HTTP/1.1의 성능 문제, 특히 HOL(Head-of-Line) Blocking 문제를 해결하고 지연 시간(Latency)를 줄이기 위해 2015년에 표준화 되었음

### 주요 특징 및 기술

- 멀티플렉싱(Multiplexing): HTTP/1.1은 하나의 TCP연결에서 요청을 순차적으로 처리해야 했지만, HTTP/2는 하나의 TCP 연결 내에서 여러 요청과 응답을 동시에 주고받을 수 있다. 메시지를 작은 프레임(Frame)단위로 쪼개어 뒤섞어(Interleaving)전송한 뒤 수신 측에서 재조립하는 방식
    - 예를 들어, 기존의 HTTP/1.1은 하나의 TCP연결만으로 비디오 클립을 전송하기 시작하면 뒤의 작은 정보들까지 긴 시간을 기다려야했음(bottleneck link)
    - 이를 해결하기 위해 HTTP/1.1에서는 일반적으로 여러 개의 병렬 TCP연결을 만드는 방식을 사용했음.
    - 이러한 방식은 병목 링크에서 TCP연결이 N개 있을 경우, 각 연결은 대역폭의 1/N을 차지함으로써 원래 사용해야할 대역폭보다 더 많은양을 사용하는 TCP 혼잡 제어 방식을 이용한 “치트” 방식이었고, 서버 입장에서는 열고 유지해야하는 소켓 수 부담이 커질 수 밖에 없었음.
- 바이너리 프레이밍(Binary Framing): 텍스트 기반이던 데이터를 바이너리 포맷으로 인코딩하여 파싱 속도를 높이고 오류 발생 가능성을 줄임.
- 헤더 압축: HPACK알고리즘을 사용하여 중복되는 헤더 정보를 압축해 전송 효율을 높임
- 서버 푸시(Server Push): 클라이언트가 요청하지 않은 리소스를 서버가 알아서 미리 보내줄 수 있어 추가적인 요청지연을 제거할 수 있다.
    - 예를 들어, HTML을 요청했을 때 아직 요청하지 않았지만 필요한 CSS나 JS파일들을 미리 보내줄 수 있음.
- 요청 우선순위(Prioritization): 클라이언트가 리소스 간의 의존성이나 중요도를 지정하여 서버가 중요한 데이터를 먼저 보내도록 할 수 있다.

### HTTP/2의 한계점

애플리케이션 계층의 HOL Blocking은 해결했지만, 여전히 TCP프로토콜 위에서 동작하도록 되어있다. 따라서 패킷 손실이 발생하면 TCP의 특성상 손실된 패킷이 재전송 될 때까지 해당 연결의 모든 스트림이 멈추는 문제(TCP 수준의 HOL Blocking)은 남아있음.

---

## HTTP/3 (QUIC & UDP)

https://datatracker.ietf.org/doc/html/rfc9114

https://datatracker.ietf.org/doc/html/rfc9000

HTTP/3는 TCP가 가진 근본적인 구조적 한계(TCP HOL Blocking, 느린 연결 설정)를 극복하기 위해, 전송 계층 프로토콜을 TCP에서 UDP 기반의 QUIC으로 교체한 차세대 프로토콜이다.

### 핵심 기술: QUIC(Quick UDP Internet Connections)

- UDP기반: QUIC은 신뢰성 보장, 혼잡 제어 등 TCP의 기능을 UDP기반으로 애플리케이션 계층에서 직접 구현한 기술이다.
- 스트림 독립성(TCP HOL Blocking 해결): 하나의 연결 안에서 여러 스트림을 독립적으로 다룬다. 따라서 패킷 하나가 손실되더라도 해당 데이터가 포함된 스트림만 영향을 받고, 다른 스트림은 정상적으로 통신이 가능.
- 빠른 연결 설정(Low Latency Handshake): TCP+TLS 구조에서는 연결 설정에 여러 번의 RTT(왕복)이 필요했지만, QUIC은 연결 설정과 보안(TLS 1.3) 핸드셰이크를 결합하여 1-RTT 또는 0-RTT(이전 연결 재사용 시)만에 통신을 시작할 수 있다.
- 보안 내장: TLS 1.3 암호화가 기본적으로 내장되어 있어 별도의 설정 없이 보안 통신을 제공
- 연결 마이그레이션: 클라이언트의 IP가 바뀌어도(ex: Wifi에서 LTE로 전환) 연결 식별자(Connection ID)를 통해 연결을 끊지 않고 유지할 수 있다.

---

**요약 비교표**

웹의 발전은 지연시간(latency)과 네트워크 효율성을 개선하는 방향으로 이루어져 왔다.

| 특징 | HTTP/1.1 | HTTP/2 | HTTP/3 |
| --- | --- | --- | --- |
| **기반 프로토콜** | TCP | TCP | **UDP (QUIC)** |
| **전송 방식** | 텍스트 (순차적) | **바이너리 프레임 (멀티플렉싱)** | 바이너리 프레임 (멀티플렉싱) |
| **HOL Blocking** | 발생 (App & TCP 계층) | **해결 (App 계층)** / 발생 (TCP 계층) | **완전 해결 (독립 스트림)** |
| **헤더 처리** | 텍스트 (압축 없음) | **HPACK 압축** | **QPACK 압축** |
| **연결 설정 속도** | 느림 (TCP + TLS) | 느림 (TCP + TLS) | **매우 빠름 (1-RTT / 0-RTT)** |
- HTTP/1.1: 연결 재사용으로 성능 개선했으나, 앞 요청이 막히면 뒤도 막히는 문제 발생(HOL Blocking)
- HTTP/2: 요청을 잘게 쪼개 섞어 보내는 방식(멀티플렉싱)으로 애플리케이션 레벨의 막힘 현상 해결.
- HTTP/3: 전송 계층을 TCP에서 UDP(QUIC)로 교체하여 패킷 손실 시 전체가 멈추는 TCP 고유의 문제까지 해결.

---

# 2.3 인터넷 전자메일(Electronic Mail in the Internet)

https://datatracker.ietf.org/doc/html/rfc5321

- 주요 구성요소: 사용자 에이전트(User Agent), 메일 서버(Mail Server), SMTP 프로토콜
- SMTP(Simple Mail Transfer Protocol): 메일을 송신하고 메일 서버 간에 메일을 전송하는 푸시(Push)프로토콜이다.
- 메일 접속 프로토콜: 수신자가 메일 서버에서 자신의 PC로 메일을 가져올 때 사용하는 풀(Pull)프로토콜이다.
    - POP3, IMAP, HTTP등의 프로토콜이 있음.

[![seukeulinsyas-2026-02-19-21-36-24.png](https://i.postimg.cc/mDdWPkZb/seukeulinsyas-2026-02-19-21-36-24.png)](https://postimg.cc/qhC5YkCY)

### 예시 시나리오:

[![seukeulinsyas-2026-02-19-21-41-57.png](https://i.postimg.cc/L5nKLSh7/seukeulinsyas-2026-02-19-21-41-57.png)](https://postimg.cc/p5b6MgfY)

1. `엘리스`가 자신의 `User agent`를 호출하여 `밥` 의 이메일 주소를 제공하며 메세지를 작성하고 `User agent` 에게 이메일을 보내도록 지시함
2. `엘리스` 의 사용자 에이전트가 메시지를 그녀의 메일 서버로 전송하고, 그곳에서 메시지 큐에 배치된다.
3. `엘리스` 의 메일 서버에서 실행되는 SMTP의 클라이언트 측에서는 메시지 큐에 있는 메시지를 확인, `밥` 의 메일 서버에서 실행되는 SMTP서버와의 TCP연결을 연다.
4. 초기 SMTP 핸드셰이크를 수행한 후, SMTP 클라이언트는 `엘리스` 의 메시지를 TCP연결로 전송
5. `밥` 의 메일 서버에서 SMTP의 서버 측이 메시지를 수신한다. `밥` 의 메일 서버는 그 후 메시지를 `밥` 의 메일함에 배치
6. `밥` 은 자신이 원하는 시간에 `User agent` 를 호출하여 메시지를 읽는다.

---

# 2.4 DNS

DNS는 사람이 기억하기 쉬운 호스트 네임(`www.google.com` 과 같은)을 컴퓨터가 통신에 사용하는 IP주소(`172.217.161.68` 처럼)로 변환해주는 인터넷의 디렉터리 서비스(Internet’s Directory Servie)이다.

## DNS의 필요성 및 특징

- 식별자 전환: 사람은 니모닉(mnemonic)한 호스트 이름을 선호하지만, 라우터는 고정 길이의 계층적 IP주소를 선호. DNS가 이 간극을 메워준다.
- 분산형 데이터베이스: DNS는 단일 서버에 모든 정보를 저장하지 않고, 전 세계에 분산된 계층적 서버들에 정보를 나누어 저장한다. 이는 단일 실패 지점(Single Point of Failure), 트래픽 집중, 거리로 인한 지연, 유지보수 문제를 해결하기 위함.
- 애플리케이션 계층 프로토콜: DNS는 UDP 프로토콜 위에서 포트 53번을 사용하여 동작함

## DNS가 제공하는 서비스

- 호스트 엘리어싱(Host Aliasing): 복잡한 정식 호스트 네임(Canonical hostname)에 대해 기억하기 쉬운 별칭(Alias)를 가지게 해준다.
    - 예를 들어, 정식 호스트 네임은 다음과 같을 수 있다 `relay1.west-coast.enterprise.com` 
    → 이를 엘리어싱하여 간단하게, `enterprise.com`
- 메일 서버 엘리어싱(Mail Server Aliasing): 웹 서버와 메일 서버가 같은 호스트 네임(`yahoo.com` 등이 있음)을 공유하면서도 메일은 메일 서버로, 웹 트래픽은 웹 서버로 가도록 구분할 수 있다.
- 부하 분산(Load Distribution): 인기 있는 사이트는 여러 대의 서버(여러 IP주소를 가지게 된다)를 운영한다. DNS는 쿼리마다 IP주소 순서를 회전시켜(DNS Rotation) 트래픽을 분산시킬 수 있음.

## DNS 서버의 계층 구조

DNS는 확장성을 위해 세 가지 유형의 서버로 계층화되어 있다.

[![seukeulinsyas-2026-02-19-21-58-22.png](https://i.postimg.cc/hPQRGKkc/seukeulinsyas-2026-02-19-21-58-22.png)](https://postimg.cc/Tpx47v24)

1. 루트 DNS서버(Root DNS Servers): 전 세계에 13개의 원본 IP주소를 가진 서버들이 1,000개 이상의 복사본으로 흩어져 있음. TLD서버의 IP주소를 제공한다.
2. 최상위 도메인(TLD) 서버(Top-Level Domain Servers): `.com` `.org` `.edu` 같은 일반 도메인과 `.kr` `.uk` 같은 국가 도메인을 관리한다. 해당 도메인에 속한 책임 DNS서버의 주소를 제공
3. 책임 DNS 서버(Authoritative DNS Servers): 실제로 특정 호스트(`www.amazon.com` 과 같은)의 IP주소 매핑 정보를 가지고 있는 서버. 서비스 제공자는 자신의 호스트 정보를 이 서버에 등록해야한다.
4. 로컬 DNS 서버(Local DNS servers): 엄밀히 말해 계층 구조에는 속하지 않지만, 호스트가 가장 먼저 쿼리를 보내는 서버이다(주로 ISP가 제공). 프록시 역할을 하며, 쿼리를 계층 구조로 전달하고 응답을 캐싱한다.

## DNS동작 과정(Resolution Process)

예를 들어 호스트가 `www.someschool.edu` 의 IP를 요청할 때의 과정은 아래와 같음.

(1) 요청: 호스트가 로컬 DNS에 질의(쿼리)를 보낸다.

(2) 루트 서버 질의: 로컬 DNS서버는 캐시에 정보가 없을 경우 루트 DNS서버에 `.edu` 를 관리하는 TLD서버가 어디인지 물어본다.

(3) TLD 서버 질의: 로컬 DNS서버는 `.edu` TLD서버에 `someschool.edu` 를 관리하는 책임 서버가 어디인지 물어본다.

(4) 책임 서버 질의: 로컬 DNS서버는 `someschool.edu` 책임 서버에 `www.someschool.edu` 의 IP주소를 물어본다.

(5) 응답: 책임 서버가 IP주소를 반환하면, 로컬 DNS 서버는 이를 호스트에게 전달한다.

[![seukeulinsyas-2026-02-19-22-01-50.png](https://i.postimg.cc/5t1hpL6x/seukeulinsyas-2026-02-19-22-01-50.png)](https://postimg.cc/RWspZ378)

- 재귀적(Recursive) vs 반복적(Iterative) 질의: 호스트가 로컬 DNS서버에 보내는 것은 “답을 알아와라”는 재귀적 질의이고, 로컬 DNS 서버가 상위 서버들에게 보내는 것은 “다음 서버 알려줄래?”라는 반복적 질의이다.

## DNS 캐싱(Caching)

DNS 성능의 핵심이 된다. DNS 서버가 질의에 대한 응답을 받으면, 그 정보를 로컬 메모리에 저장한다.

→ 이후 동일한 질의가 오면, 상위 서버(루트나 TLD)를 거치지 않고 즉시 응답

→ TTL(Time To Live): 캐시된 정보는 영구적이지 않으며 TTL 시간이 지나면 삭제된다.

## DNS 레코드와 메시지

DNS 서버는 자원 레코드(Resource Record, `RR`)를 저장한다. `RR` 은 (`Name` , `Value` , `Type` , `TTL` )의 4가지 필드로 구성된다.

- `Type = A`: `Name`은 호스트 네임, `Value` 는 IPv4주소가 된다. 가장 기본
    - (`Name: relay1.bar.foo.com` , `145.37.93.126` , `A` )
- `Type = NS`: `Name`은 도메인, `Value` 는 해당 도메인의 책임 DNS서버 호스트 네임이 된다.
    - (`Name: foo.com` , `Value: dns.foo.com` , `NS`)
- `Type=CNAME`: `Name`은 별칭, `Value`는 정식 호스트 네임
    - (`Name: foo.com` , `Value: relay1.bar.foo.com` , `CNAME`)
- `Type=MX`: `Name`은 별칭, `Value`는 메일 서버의 정식 호스트 네임
    - (`Name: foo.com` , `Value: mail.bar.foo.com` , `MX`)

DNS 메시지는 헤더(식별자, 플래그), 질문(Question), 답변(Answer), 권한(Authority), 추가 정보(Additional)섹션으로 구성된다.

[![seukeulinsyas-2026-02-19-22-12-57.png](https://i.postimg.cc/gjf5h6Cn/seukeulinsyas-2026-02-19-22-12-57.png)](https://postimg.cc/p5JqbyXH)

# 2.5 P2P 파일 분배 (Peer-to-Peer File Distribution)

- BitTorrent: 파일 분배를 위한 대표적인 P2P 프로토콜. 파일은 청크(Chunk) 단위로 나뉘며, 피어들은 서로 없는 청크를 교환합니다. 'Tit-for-Tat' 전략을 사용하여 자신에게 데이터를 잘 보내주는 피어에게 우선적으로 데이터를 보냅니다.

# 2.6 비디오 스트리밍과 콘텐츠 분배 네트워크 (Video Streaming and CDNs)

- DASH (Dynamic Adaptive Streaming over HTTP): 비디오를 여러 품질 버전으로 인코딩하여 저장하고, 클라이언트가 네트워크 상태에 맞춰 적절한 품질의 청크를 동적으로 요청하는 방식입니다.
- CDN (Content Distribution Network): 전 세계에 분산된 서버에 콘텐츠 복사본을 저장하여 사용자가 지리적으로 가까운 서버에서 빠르게 콘텐츠를 다운로드할 수 있게 합니다.

[![seukeulinsyas-2026-02-19-22-15-33.png](https://i.postimg.cc/h4wN6HXK/seukeulinsyas-2026-02-19-22-15-33.png)](https://postimg.cc/8sRyrXdY)

---