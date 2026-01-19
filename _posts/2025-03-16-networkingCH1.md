---
title: "네트워크 기본서 Chapter1.2_Computer Networks And The Internet"
date: 2025-03-16 09:00:00 +0900
categories: [DevOps]
tags: [devops]
---
# 1.2 The Network Edge

End Systems are also refferd to as <b>host</b>

end systems includes

- Desktop Computers(desktop PCs, Macs, Linux boxes)
- servers (e.g., Web and Email servers)
- mobile devices (e.g., laptops, smartphones, and tablets)
- non-traditional "things"

host = end system
<br>
-> divided into two categories: <b>clients</b> and <b>servers</b>

<br><br>

## 1.2.1 Access Networks

access network-- the network that physically connects and end system to the first router(also known as the "edge router")

![Image](https://github.com/user-attachments/assets/ba08d54b-7b98-456d-9c82-73cd24ccd6ea)

<br>

### Home Access: DSL, Cable, FTTH, and 5G Fixed Wireless

#### DSL: Digital Subscriber Line

A residence typically obtains DSL Internet access from the same local
telephone company(telco) that provides its wired local phone access.

when DSL is used, telco = ISP

![Image](https://github.com/user-attachments/assets/f5d620ab-71fd-4919-b65c-a245046c4962)

- customer's DSL modem uses the existing telephone line exchange data with a <i>Digital subscriber line access multiplexer(DSLAM)</i>

- DSLAM located in the telco's local central office(CO)

- customer's DSL modem takes digital data and translates it to high-frequency tones for transmission over telephone wires to the CO.

- the analog signals -> translated back into digital format at the DSLAM

> The residential telephone line carries both data and traditional telephone siganls simultaneously, which are encoded at different frequencies:

- A high-speed downstream channel, in the 50kHz to 1MHz band

- A medium-speed upstream channel, in the 4kHz to 50kHz band

- An ordinary two- way telephone channel, in the 0 to 4kHz band

customer side: splitter separates arriving signals(telephone / data)

telco(CO) side: DSLAM separates arriving signals(telephone / data)<br>
-> hundreds or even thousands of households connect to a single DSLAM

> DSL standards define multiple transmission rates:<br>
> downstream transmission rates of 24Mbs and 52Mbs<br>
> upstream rates of 3.5Mbps and 16Mbps<br>
> -> the access is said to be asymmetric

#### Cable Internet Access

> <i>Cable Internet Access</i> makes use of the <b>cable television company's existing cable television infrastructure</b>

![Image](https://github.com/user-attachments/assets/5466bc8b-c058-4468-b816-d973518bb8ac)

- fiber optics connect the cable head end to nighborhood-level junctions.
- coaxial cable is then used to reach individual houses and apartments

> Both fiber and coaxial cable are employed -> reffered to as <i>hybrid fiber coax(HFC)</i>

- <i>cable modems</i> is typically employed to connect home PC through an Ethernet port

- at the cable head end, <i>cable modem termination system(CMTS)</i> serves a similar functino as the DSL network's DSLAM

- As with DSL, access is typically asymmetric: DOCSIS 2.0 and 3.0 standards define:<br>
  downstream biterates of 40Mbps and 1.2 Gbps<br>
  upstream rates of 30Mbps and 100Mbps

> One important characteristic: cable internet access is a shared borad-cast medium.<br>

1. every packet sent by the head end -> travels on the downstream on every link to every home<br>
2. every packet sent by a home -> travels on the upstream channel to the head end.

this characteristic causes:<br>

- if several users are simultaneously down-loading a video file on the downstream channel, the actual rate at which each user recives its video file will be significantly lower than the aggregate cable downstream rate.

- if there are only a few active users and they are all Web surfing, then each of the users may actuallly receive Web pages at the full cable downstream rate. (beacause the users will rarely request Web pages at exactly the same time)

> Because the upstream channel is also shared, a distributed multiple access protocol is needed to coordinate transmissions and avoid collisions.

#### fiber to the home(FTTH)

as the name suggests simple, <br>
-> <b>provide and optical fiber path from the CO directly to the home.</b> (potentially provide Internet access rates in the gigabits per sec range)

1. the simplest opticla distribution network is called direct fiber<br>
   -> with one fiber leaving the CO for each home.(expansive)

- each fiber leaving the CO is actually shared by many homes; fiber gets relatively close to the homes that it is split into individual customer-specific fibers. <br>
  -> there are two competing optical-distribution network architectures

2. <i>active optical networks(AONs)</i>: <br>
   essentially switched Ethernet (discussed in Chapter 6)

![Image](https://github.com/user-attachments/assets/3e6c8a7d-7736-4f89-a6a7-d4a8e2d4833c)

3. <i>passive optical networks(PONs)</i>: <br>

- each home has <i>optical network terminator(ONT)</i>, which is connected by dedicated optical fiber to a neighborhood splitter.
- the splitter combines a number of homes(less than 100) onto a single, shared optical fiber, which connects to an <i>optical line terminator(OLT)</i> in the telco's CO.
- OLT providing conversion between optical and electical signals, connects to the internet via a telco router.

> In PON architecture, all packets sent from OLT to the splitter are replicated at the splitter (similar to a cable head end).

#### Access in the Enterprise(and the Home): Ethernet and WiFi

> <i>local area network(LAN)</i> is used to connect an end system to the edge router.<br>
> Ethernet is by far the most prevalent access technology in corporate, university, and home networks.

> Ethernet users use twisted-pair copper wire to connect to an Ethernet swich. switches is then in turn connected into the larger Internet.

- Ethernet access, users typically have 100Mbps to tens of Gbps access to the Ethernet switch, whereas servers may have 1Gbps 10Gbps access.

![Image](https://github.com/user-attachments/assets/92b4fdfe-42f0-4ae8-967d-9400007e5c2a)

- many home combine broadband residential access(cable modem or DSL) with these inexpensive wireless LAN technologies to creatoe powerful home networks (WiFi, IEEE 802.11 defined)

![Image](https://github.com/user-attachments/assets/0ebc1d12-4f63-49a2-afce-6a19de025442)

## 1.2.2 Physical Media

guided media: <i>twisted-pair copper wire, coaxial cable, multimode fiber-optic cable</i> <br>

unguided media: <i>terrestrial radio spectrum, and satellite radio spectrum.</i>

### Twisted-Pair Copper Wire

> The least expensive and most commonly used guided transmission medium

- Twisted pair consists of two insulated copper wires, each about 1mm thick, arranged in a regular spiral pattern. the wires are twisted together to reduce the electrical interference from similar pairs close by.

- <b>Unshielded twisted pair(UTP)</b> is commnly used for computer networks for LANs.(range from 10Mbps to 10Gbps)

### Coaxial Cable

> consists of two copper conductors, but the two conductors are concentric rather than parallel.

- with this construction and special insulation and shielding, coaxial cable can achieve high data transmission rates.

- coaxial cable acn be used as a guided shared medium. a number of end systems can be connected directly to the cable, with each of the end systems receiving whatever is sent by the other end systems.

- common in cable television systems.(rates of hundreds of Mbps)

### Fiber Optics

> thin, flexible medium that conducts pulses of light, with each pulse representing a bit.

- immune to electromagnetic interference, have very low signal attenuation up to 100kilometers, and are very hard to tap.

- preferred long-haul guided transmission media, particulary for overseas links. and also prevalent in the backbone of the Internet.
  but in LAN or into the home, its too high cost.

- Optical Carrier(OC) standard link speeds range from 51.8Mbps to 39.8Gbps; these specifications are often referred to as OC-n, where the link speed equals n X 51.8Mbps. standards in use today include OC-1, OC-3, OC-12, OC-24, OC-48, OC-96, OC-192, OC-768.
