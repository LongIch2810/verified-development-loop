# Verified Development Loop (VDL)

VDL là một **agent skill** dùng lại được trong nhiều dự án phần mềm. Khi bạn yêu cầu chạy VDL, agent sẽ đi qua một quy trình có bằng chứng: làm rõ yêu cầu → viết Spec và Plan → xin duyệt → phát triển bằng TDD → chạy kiểm tra → review độc lập → QA → báo cáo kết quả.

Skill giúp tránh việc agent tự đổi yêu cầu, bỏ qua kiểm tra hoặc báo hoàn thành khi chưa có bằng chứng. Nó chỉ kích hoạt khi bạn yêu cầu VDL hoặc yêu cầu rõ quy trình trên; các chỉnh sửa và câu hỏi thông thường không tự khởi chạy workflow.

## Repo này gồm những gì?

Mã nguồn skill nằm trong `skills/vdl-verified-development-loop/`; khi cài vào dự án, Skills CLI đặt bản sao vào thư mục skill của agent.

- [Skill chính](skills/vdl-verified-development-loop/SKILL.md): hướng dẫn agent điều phối các bước và điều kiện chuyển trạng thái.
- `agents/`: bốn vai trò planner, TDD coder, code reviewer và QA tester. Agent chính giao việc cho subagent của host đang dùng; các file này không tự tạo agent.
- `assets/templates/`: ba mẫu Spec, Plan và QA report.
- `scripts/workflow.py`: lưu trạng thái, chạy lệnh kiểm tra đã duyệt và ghi bằng chứng vào `.verified-development-loop/` của dự án sử dụng skill.
- `scripts/control_center.py`: dashboard xem tiến độ và sự kiện tại `http://127.0.0.1:4040`.
- `scripts/install_vdl.py`: khởi tạo thư mục workflow, cấu hình hook và mở Control Center. Các test bảo trì repo nằm trong `tests/` và không được cài theo skill.
- [LICENSE](LICENSE): giấy phép MIT. [CHANGELOG.md](CHANGELOG.md) ghi các thay đổi chưa phát hành.

VDL yêu cầu **Python 3.11+**, Git và một agent có thể đọc skill, chạy lệnh Python, giao việc cho subagent độc lập. Nếu host không hỗ trợ subagent, agent phải báo giới hạn đó; không được giả nhận đã có review hoặc QA độc lập.

## Cài skill vào dự án

Chạy trong thư mục dự án cần dùng VDL:

```sh
npx skills add LongIch2810/verified-development-loop --skill vdl-verified-development-loop --copy -y
```

`npx skills` tự tìm các agent đã cài trên máy và chép skill vào thư mục tương ứng. Ví dụ Codex và Cursor dùng `.agents/skills/`, còn Claude Code nhận thêm bản trong `.claude/skills/`. Không cần tạo npm package; [Skills CLI cài trực tiếp từ Git repo](https://github.com/vercel-labs/skills#source-formats).

### Khởi tạo workflow, hook và Control Center

**Lệnh `npx skills add` chỉ chép skill; nó không chạy script cài đặt hoặc tự kích hoạt hook.** Sau khi cài, chạy thêm trong cùng dự án:

```sh
python .agents/skills/vdl-verified-development-loop/scripts/install_vdl.py --target .
```

Trên macOS và Linux, dùng `python3` thay cho `python`. Lệnh tạo thư mục `.verified-development-loop/`, thêm `.vdl/` vào `.gitignore` và mở Control Center. Trên **Windows, macOS và Linux**, mặc định nó đăng ký hook vòng đời cho Codex, Claude Code và Cursor; các hook này giúp dashboard quan sát phiên làm việc và subagent. Muốn chỉ cài hook cho một host, dùng `--no-hooks` kèm đúng cờ của host đó, ví dụ:

```sh
python .agents/skills/vdl-verified-development-loop/scripts/install_vdl.py --target . --no-hooks --codex-hooks
```

Thay `--codex-hooks` bằng `--claude-hooks` hoặc `--cursor-hooks` khi cần; có thể dùng nhiều cờ cùng lúc. Dùng `--no-control-center` nếu chưa muốn mở dashboard.

Workflow vẫn ghi các mốc mà agent chủ động gọi qua `workflow.py emit` và các lệnh chuyển trạng thái. **Không có hook, Control Center không thể tự quan sát prompt, phiên làm việc hoặc subagent.** Installer dùng launcher `.cmd` trên Windows và `python3` trên macOS/Linux. Host khác ngoài Codex, Claude Code và Cursor cần adapter hook riêng để quan sát thụ động. Xem [hướng dẫn portability](skills/vdl-verified-development-loop/references/portability.md) và [theo dõi sự kiện](skills/vdl-verified-development-loop/references/tracking.md).

## Sử dụng

Trong agent đã cài skill, yêu cầu rõ ràng, chẳng hạn: “Hãy dùng `$vdl-verified-development-loop` để triển khai tính năng này.” Agent sẽ chuẩn bị Spec, Plan và kịch bản QA để bạn duyệt trước khi sửa mã ứng dụng. Sau khi duyệt, nó mới thực hiện TDD, verification, review và QA theo [quy trình của skill](skills/vdl-verified-development-loop/SKILL.md).

## Public skill này

Repo đã được public trên GitHub. Có thể kiểm tra skill được nhận diện bằng lệnh:

```sh
npx skills add LongIch2810/verified-development-loop --list
```
