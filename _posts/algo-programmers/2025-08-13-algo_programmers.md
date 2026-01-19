---
title: "[알고리즘] 고득점Kit_정렬/해시 level 1 풀이"
date: 2025-08-13 09:00:00 +0900
categories: [Algorithm]
tags: [problem-solving, algorithm]
---
## 정렬 - K번째 수

[문제링크](https://school.programmers.co.kr/learn/courses/30/lessons/42748?language=java)

풀이

```java
import java.util.*;

class Solution {
    public int[] solution(int[] array, int[][] commands) {
        // Scanner sc = new Scanner(System.in);
        int[] answer = new int[commands.length];
        int num=0;

        for(int[] c : commands){
            int i = c[0] - 1;
            int j = c[1];
            int k = c[2] - 1;

            int[] subArray = new int[j - i];
            for (int l = i; l < j; l++) {
                subArray[l - i] = array[l];
            }

            Arrays.sort(subArray);

            answer[num++] = subArray[k];
        }

        return answer;
    }
}
```

> 간단 설명

- 정렬은 stl사용 / 구현에 초점 맞췄음
  - i,j,k를 command[] 에서 받아오고
  - subArray에 i~j번째 원본 숫자를 복사해주고
  - 정렬한 뒤, k번째 숫자를 answer배열에 순서대로 넣어줬다

<hr/>
<hr/>

## 해시 - 완주하지 못한 선수

[문제링크](https://school.programmers.co.kr/learn/courses/30/lessons/42576)

풀이

```java
import java.util.HashMap;

class Solution {
    public String solution(String[] participant, String[] completion) {
        String answer = "";

        HashMap<String, Integer> map = new HashMap<>();
        for(String p : participant)
            map.put(p, map.getOrDefault(p, 0) + 1); // 참가자 동명이인에 대한 처리

        for(String c : completion)
            map.put(c, map.get(c) - 1);

        for(String key : map.keySet()) {
            if(map.get(key) != 0){
                answer = key;
            }
        }
        return answer;
    }
}
```

> 설명

- 해시맵으로 Key를 참가자이름 - Value로 동명의 인원 수를 카운트함
  - 첫번째 participant 순회에서는 입력받은 key값에 동명이인이 있으면 value를 +1처리, 아니면 기본값으로 0으로 처리함
  - completion 순회하는 for문에서는 해당 key값이 걸릴때마다 -1씩 처리
  - 마지막 map에 들어있는 Key를 순회하며 0이 아닌 값(0보다 큰값)이라면 참여했지만 완주하지 못한 사람이라는 뜻이므로 해당 선수를 답으로 리턴함
  - 완주하지못한 “단 한명의 선수”를 찾는 거기 때문에 바로 리턴하도록 처리했음
