-- 생성: 2026-10-21 23:40 (KST)
-- 팀 편성 앱의 tf_ 테이블 (공고 5장). Supabase SQL 편집기에서 그대로 실행할 수 있음.
-- 같은 DB에 6장 실습 테이블이 함께 있으므로 이 과제의 테이블은 모두 tf_ 로 시작함.

create table if not exists tf_students (
    id            bigint generated always as identity primary key,
    student_no    text not null unique,                -- 학번, 유일
    name          text not null,
    main_role     text check (main_role in ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    password_hash text not null,                       -- bcrypt 해시. 비밀번호를 그대로 저장하지 않음
    is_admin      boolean not null default false,
    check (is_admin or main_role is not null)          -- 학생은 주 역할이 꼭 있음
);

create table if not exists tf_student_sub_roles (
    student_id bigint not null references tf_students(id) on delete cascade,
    role       text not null check (role in ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    position   smallint not null default 1,            -- CSV에 적힌 순서
    primary key (student_id, role)
);

create table if not exists tf_teams (
    id   integer primary key,                           -- 팀 번호 (팀1 → 1)
    name text not null unique
);

-- 팀원. (team_id, slot_no) 기본 키와 student_id 유일성 제약이
-- "마지막 자리에 두 명이 동시에 들어감"(먼저 도착한 학생만 기록)과 "한 학생은 한 팀"을 DB에서 지킴
create table if not exists tf_members (
    team_id    integer not null references tf_teams(id) on delete cascade,
    slot_no    integer not null check (slot_no between 1 and 4),
    student_id bigint  not null unique references tf_students(id) on delete cascade,
    primary key (team_id, slot_no)
);

create table if not exists tf_applications (
    id         bigint generated always as identity primary key,
    team_id    integer not null references tf_teams(id) on delete cascade,
    student_id bigint  not null references tf_students(id) on delete cascade,
    status     text not null default '대기' check (status in ('대기', '승인', '거절')),
    reason     text,
    created_at timestamptz not null default now(),
    decided_at timestamptz
);

-- 한 학생은 결과를 기다리는 지원을 하나만 가질 수 있음
create unique index if not exists tf_one_pending on tf_applications(student_id) where status = '대기';

create table if not exists tf_votes (
    application_id bigint not null references tf_applications(id) on delete cascade,
    voter_id       bigint not null references tf_students(id) on delete cascade,
    vote           text not null check (vote in ('찬성', '거부')),
    created_at     timestamptz not null default now(),
    primary key (application_id, voter_id)              -- 한 번 투표하면 바꿀 수 없음
);

create table if not exists tf_settings (
    key   text primary key,                             -- closed(마감 여부), pending_plan(확정 전 배정안)
    value text not null
);

create table if not exists tf_ai_logs (
    id         bigint generated always as identity primary key,
    tier       integer not null,                        -- 1차, 2차, 3차
    model      text not null,
    outcome    text not null,                           -- 성공, 실패
    detail     text not null default '',
    elapsed_ms integer not null,
    created_at timestamptz not null default now()
);

-- Supabase의 공개 API(PostgREST)로 이 테이블을 읽고 쓰지 못하게 RLS를 켬.
-- 앱은 DATABASE_URL(postgres 사용자)로 직접 연결하므로 영향이 없음.
alter table tf_students          enable row level security;
alter table tf_student_sub_roles enable row level security;
alter table tf_teams             enable row level security;
alter table tf_members           enable row level security;
alter table tf_applications      enable row level security;
alter table tf_votes             enable row level security;
alter table tf_settings          enable row level security;
alter table tf_ai_logs           enable row level security;
