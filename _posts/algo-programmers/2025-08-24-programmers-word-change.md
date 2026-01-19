---
title: "[알고리즘] 프로그래머스 단어변환 풀이"
date: 2025-08-24 09:00:00 +0900
categories: [Algorithm]
tags: [problem-solving, programmers, algorithm]
---
[![2025-08-24-17-36-39.png](https://i.postimg.cc/JhdkvNNJ/2025-08-24-17-36-39.png)](https://postimg.cc/XZdqyyD7)

```java
class Solution {
    public int solution(String begin, String target, String[] words) {
        int n = words.length;
        int targetIdx = -1;

        for(int i=0; i<n; i++)
            if(words[i].equals(target))
                targetIdx = i;
        if(targetIdx == -1)
            return 0;

        int[] dist = new int[n];
        Queue<Integer> q = new ArrayDeque<>();

        for(int i=0; i<n; i++){
            if(oneDiff(begin, words[i])) {
                dist[i] = 1;
                q.offer(i);
            }
        }

        while(!q.isEmpty()){
            int cur = q.poll();
            if(cur == targetIdx) return dist[cur];

            for(int nxt=0; nxt<n; nxt++){
                if(dist[nxt]==0 && oneDiff(words[cur], words[nxt])){
                    dist[nxt] = dist[cur] + 1;
                    q.offer(nxt);
                }
            }
        }
        return 0;
    }

    boolean oneDiff(String a, String b){
        if(a.length() != b.length()) return false;
        int diff = 0;
        for(int i=0; i<a.length(); i++)
            if(a.charAt(i) != b.charAt(i) && ++diff > 1) return false;

        return diff == 1;
    }
}
```

## 풀이 설명

단어를 한글짜씩 바꿔가면서 target으로 주어진 단어에 도달할 수 있는 최소경로를 계산하는 문제입니다.

- boolena oneDiff(String a, String b)는 주어진 두개의 단어가 한글자씩만 다른지를 검사하는 메소드입니다.

- dist[] 배열에는 문제에서 begin으로 주어지는 단어로부터의 거리(한글자만 바꾸면 1, 두글자 바꾸면 2)가 저장됩니다.

- bfs로 최단거리를 탐색하는데, 이때 큐에는 words에서의 인덱스만 저장합니다.

- 당연하게도, 큐에 넣고 bfs를 돌리다가 targetIdx와 일치하는 즉, 원하는 타겟에 도달하면 해당 거리(== 최소 변환횟수)를 반환합니다.

- bfs가 다 끝나도 if(cur==targetIdx)에 걸리지 않았다면 변환이 불가능하다는 뜻이므로 0을 반환합니다.

- 문제에서 주어진 조건이 "모든 단어의 길이는 같음", "중복되는 단어는 없음"에 유의할 필요가 있습니다.

> 💡 AI가 집어주는 이문제가 BFS가 정석인 이유
>
> - 문제에서 "최단변환 횟수"를 묻기 때문에 BFS가 자연스럽게 최단 거리를 보장함
> - 아래처럼 DFS로 탐색할 경우 target을 처음 만났을 때가 반드시 최단 경로라고 보장할 수 없음
>
> ```java
> begin -> A -> B -> target (3단계)
> begin -> C -> target      (2단계)
> ```
>
> ✨ BFS의 방식자체로서,
>
> - beins에서 거리 1인 단어들 -> 거리 2 -> 거리 3 순서대로 탐색하기 때문에 최단거리 보장된다.
> - DFS로 풀려면, 반드시 모든 경로 탐색 + 최솟값 갱신 과정을 넣어줘야 한다!!
