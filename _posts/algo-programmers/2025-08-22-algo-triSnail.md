---
title: "[알고리즘] 프로그래머스 삼각 달팽이 풀이"
date: 2025-08-22 09:00:00 +0900
categories: [Algorithm]
tags: [problem-solving, programmers, algorithm]
---
```cpp
#include <bits/stdc++.h>
using namespace std;

vector<int> solution(int n) {
    vector<vector<int>> board(n, vector<int>(n, 0));
    int y = 0, x = 0, dir = 0;
    int dy[3] = {1, 0, -1};
    int dx[3] = {0, 1, -1};

    int num = 1, total = n * (n + 1) / 2;

    while (num <= total) {
        board[y][x] = num++;

        int ny = y + dy[dir];
        int nx = x + dx[dir];

        if (ny < 0 || ny >= n || nx < 0 || nx >= n || board[ny][nx] != 0 || nx > ny) {
            dir = (dir + 1) % 3;
            ny = y + dy[dir];
            nx = x + dx[dir];
        }

        y = ny;
        x = nx;
    }

    vector<int> answer;
    for (int i = 0; i < n; ++i)
        for (int j = 0; j <= i; ++j)
            answer.push_back(board[i][j]);

    return answer;
}
```

[![2025-08-22-12-13-09.png](https://i.postimg.cc/HLQy2pQy/2025-08-22-12-13-09.png)](https://postimg.cc/yJ8x6Cp1)

- 처음에 삼각형의 왼쪽 빗변, 밑변, 오른쪽 빗변을 반복하는 패턴이라 재귀로 접근했었다.
- 근데 오히려 구현이 더 어려워지는 것 같아서 BFS에서 쓰던 방향잡아서 2차원배열에 접근하는 구현을 했다.

[![image.png](https://i.postimg.cc/wBjh61ZQ/image.png)](https://postimg.cc/75jC9Zx5)

- 위 이미지와 같이 2차연 배열인 board에 dy, dx를 이용한 증감방향을 잡아서 인덱스에 접근하게 된다.

- 결과적으로 아래 이미지와 같이 2차원 배열에 삼각형 모양으로 원하는 숫자들이 채워지고, 여기에 마지막에 for문으로 접근해서 1차원으로 펴주는 작업을 했다

[![image.png](https://i.postimg.cc/tRxFCQSw/image.png)](https://postimg.cc/vDG43jdt)
