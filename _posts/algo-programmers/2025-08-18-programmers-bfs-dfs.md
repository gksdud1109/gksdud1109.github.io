---
title: "[알고리즘] 고득점Kit_BFS/DFS level 1 풀이"
date: 2025-08-18 09:00:00 +0900
categories: [Algorithm]
tags: [problem-solving, algorithm]
---
[타겟 넘버](https://school.programmers.co.kr/learn/courses/30/lessons/43165?language=java)

```java
class Solution {
    public int solution(int[] numbers, int target) {
        int answer = 0;
        return plusminus(numbers, 0, 0, target);
    }
    public int plusminus(int[] numbers, int index, int sum, int target){
        if(index>= numbers.length)
            return (sum==target) ? 1 : 0;

        int plus = plusminus(numbers, index+1, sum+numbers[index], target);
        int minus = plusminus(numbers, index+1, sum-numbers[index], target);

        return plus + minus;
    }
}
```

> 설명

- 배열과 target을 전역으로 줄 수 있었다면 더 깔끔할 수 있었을 것 같습니다..
- “정수들의 순서를 바꾸지 않고” 적절히 더하거나 빼서 타겟넘버를 만드는 문제입니다
- 같은 자리에서 +, -의 분기만 처리해주면 됩니다
- numbers에 담긴 숫자를 index순으로 순회합니다
- 베이스 컨디션에 도달하면 target에 맞을경우 1, 다른 숫자일 경우 0을 반환합니다(타겟넘버를 만드는 방법을 카운팅하는 것이므로)
- 각 분기에서 리턴이 착착 넘어오면 결국 최종 리턴값에 타겟 넘버를 만드는 방법의 수가 쌓이게 됩니다.

---

[네트워크](https://school.programmers.co.kr/learn/courses/30/lessons/43162?language=java)

```java
import java.util.*;

class Solution {
    public int solution(int n, int[][] computers) {
        int networks = 0;
        boolean[] vis = new boolean[205];

        for(int i=0; i<n; i++){
            if(vis[i]) continue;
            networks++;

            Queue<Integer> Q = new ArrayDeque<>();
            Q.add(i);
            vis[i] = true;

            while(!Q.isEmpty()){
                int cur = Q.remove();
                for(int nxt =0; nxt < n; nxt++){
                    if(computers[cur][nxt] == 1 && !vis[nxt]){
                        vis[nxt] = true;
                        Q.add(nxt);
                    }
                }
            }
        }
        return networks;
    }
}
```

> 설명

- vis 배열은 해당 컴퓨터를 방문했는지 여부를 체크합니다 크기는 그냥 205로 잡아놓습니다.
- for문을 돌며 순회하되, vis에 방문했다 되어있는건 건너뜁니다.
- vis에 방문하지 않았다고 되어있는 컴퓨터가 걸리면 새 네트워크를 찾은것이므로 일단 networks를 하나 늘려줍니다.
- Q를 선언해서 현재 방문중인 컴퓨터 인덱스 번호를 집어넣고 vis에 방문했다 체크해줍니다.
- 현재 컴퓨터와 연결된 컴퓨터 정보를 nxt로 순회하며 배열에 저장된 값이 1이고, 방문하지 않은 컴퓨터들을 전부 찾아 vis에는 체크, Q에다 담아줍니다
- 이과정을 Q가 비어있을 게 될때까지 하게되면 연결되어있는 하나의 네트워크를 다 탐색하게 됩니다.

[참고한 곳](https://blog.encrypted.gg/941)<br/>

[![image.webp](https://i.postimg.cc/yxRqzSCG/image.webp)](https://postimg.cc/0K9XYjQG)

[자바 Queue 메소드](https://cocoon1787.tistory.com/774)
