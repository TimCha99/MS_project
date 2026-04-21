# MS_project
Museum Security Robot Project (Doosan AMR Final Project)

# MS_project 협업 가이드 (필독!)

우리 팀의 원활한 코드 공유를 위해 아래의 깃(Git) 사용법과 주의사항을 반드시 지켜주세요.

## 1. 처음 시작할 때 (Clone)
레포지토리를 내 컴퓨터로 처음 가져올 때 한 번만 실행합니다.
- `git clone [레포지토리_URL]`

## 2. 매일 작업 시작 전 (Pull) - ⭐가장 중요⭐
다른 팀원이 수정한 내용을 내 컴퓨터에 반영하는 과정입니다. **작업 시작 전 무조건 실행하세요.**
- `git pull origin main`
- **주의:** 이걸 안 하고 코드를 짜면 나중에 코드가 꼬여서(Conflict) 수습하기 힘들어집니다.

## 3. 내가 짠 코드 올리기 (Add, Commit, Push)
수정한 코드를 깃허브 서버에 저장하는 과정입니다.
1. `git add .` : 내가 수정한 모든 파일을 올릴 준비를 합니다.
2. `git commit -m "수정내용 요약"` : 어떤 부분을 고쳤는지 짧게 기록합니다.
3. `git push origin main` : 깃허브 서버로 내 코드를 보냅니다.

---

## ⚠️ 절대 주의사항 (중요!)

### 🚫 빌드 파일 업로드 금지 (.gitignore 미설정 상태)
현재 우리 프로젝트는 빌드 결과물을 자동으로 걸러주는 설정이 되어 있지 않습니다.
- **`build/`, `install/`, `log/` 폴더는 절대 올리지 마세요!**
- 실수로 이 폴더들을 `add`했다면 `push`하기 전에 꼭 확인해 주세요. 용량이 커서 전체 시스템이 느려집니다.

### 🚫 코드 충돌 주의
- 같은 파일의 같은 줄을 두 명이 동시에 고치면 에러가 납니다. 작업할 파일은 미리 팀원들과 공유해 주세요.
- `push`가 안 된다면 대부분 `pull`을 먼저 안 해서 그런 것이니, `pull`부터 다시 시도해 보세요.

<img width="1024" height="559" alt="image" src="https://github.com/user-attachments/assets/aff2e684-0459-4d92-b67a-2f555969a422" />
