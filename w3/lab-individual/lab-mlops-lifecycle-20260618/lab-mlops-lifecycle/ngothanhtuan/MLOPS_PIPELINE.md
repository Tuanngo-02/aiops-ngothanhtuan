# Hướng Dẫn Vận Hành & Kiến Trúc Hệ Thống MLOps Anomaly Detection

Tài liệu này tổng hợp toàn bộ các công việc đã thực hiện, mô tả kiến trúc pipeline hệ thống và cung cấp hướng dẫn từng bước để bạn tự chạy và kiểm thử hệ thống.

---

## 1. Các Công Việc Đã Thực Hiện

Chúng tôi đã hoàn thiện toàn bộ các file giải pháp chất lượng cao và đặt trong thư mục **`ngothanhtuan/`** (đường dẫn: [ngothanhtuan/](file:///d:/Xbrain_BT/aiops-ngothanhtuan/w3/lab-individual/lab-mlops-lifecycle-20260618/lab-mlops-lifecycle/ngothanhtuan/)):

1. **`pipeline.py`**: Script huấn luyện mô hình Isolation Forest. Điểm cải tiến quan trọng là đóng gói `StandardScaler` và `IsolationForest` vào một **scikit-learn `Pipeline`**. Điều này giúp mô hình tự động chuẩn hóa dữ liệu khi dự báo (inference) hoặc đánh giá hiệu năng, khắc phục lỗi không chuẩn hóa dữ liệu ở phần inference của code mẫu.
2. **`serve.py`**: API FastAPI phục vụ mô hình (`POST /predict`, `GET /health/active-version`, `POST /reload` và `GET /metrics`). Tải mô hình thông qua MLflow Model Registry alias `@production` để thực hiện Blue-Green deployment.
3. **`drift_detector.py`**: Wrapper cho Evidently AI. Hỗ trợ 3 chế độ check: `data` (Data Drift), `performance` (Concept/Performance Drift), và `combined` (kết hợp cả hai).
4. **`retrain.py`**: Script điều phối (Orchestrator) toàn bộ vòng đời: kiểm tra drift $\rightarrow$ gộp dữ liệu theo cửa sổ trượt (sliding window) $\rightarrow$ train v2 $\rightarrow$ validate holdout $\rightarrow$ đăng ký staging $\rightarrow$ hỏi phê duyệt $\rightarrow$ thăng cấp production $\rightarrow$ reload server $\rightarrow$ giám sát 24 chu kỳ $\rightarrow$ tự động rollback về v1 nếu precision < 0.65.
5. **`metrics_util.py`**: Công cụ đẩy các chỉ số vận hành lên Prometheus Pushgateway để hiển thị trực quan lên Grafana.
6. **`DESIGN.md`**: Tài liệu thiết kế hệ thống, biện minh thông số kỹ thuật (drift threshold 0.15, sliding-window, auto-rollback threshold 0.65).
7. **`SUBMIT.md`**: Bài thu hoạch trả lời chi tiết 5 câu hỏi phản định với số liệu thực nghiệm cụ thể.
8. **`README.md`**: Hướng dẫn tóm tắt quy trình chạy bằng một đoạn văn ngắn gọn.

---

## 2. Kiến Trúc Hệ Thống (MLOps Pipeline)

Luồng hoạt động của hệ thống được mô tả qua sơ đồ dưới đây:

```mermaid
graph TD
    %% Dữ liệu
    subgraph Data Layer
        A[baseline.csv - 30 ngày]
        B[drifted.csv - 7 ngày]
        C[holdout.csv - Kiểm định]
        D[post_deploy_eval.csv - Giám sát]
    end

    %% Train v1
    subgraph Training Phase
        A -->|Đầu vào| E[pipeline.py]
        E -->|Huấn luyện Pipeline| F(Scaler + IsolationForest)
        F -->|Đăng ký model| G[(MLflow Model Registry)]
        G -->|Thiết lập alias| H[models:/anomaly-detector@production]
    end

    %% Serve v1
    subgraph Serving Phase
        H -->|Tải mô hình| I[serve.py - FastAPI port 8000]
        I -->|Endpoints| J1[POST /predict]
        I -->|Endpoints| J2[GET /health/active-version]
        I -->|Endpoints| J3[POST /reload]
        I -->|Metrics| K[Prometheus scraping /metrics]
    end

    %% Giám sát Drift & Retrain
    subgraph Drift & Retrain Phase
        B -->|Dữ liệu mới| L[drift_detector.py]
        A -->|Dữ liệu tham chiếu| L
        L -->|Chế độ Combined| M{Drift hoặc Hiệu năng giảm?}
        M -->|Không| N[Kết thúc - Giữ nguyên v1]
        M -->|Có| O[retrain.py - Huấn luyện lại v2]
        
        %% Retrain logic
        O -->|Gộp Baseline + Drift| P[Sliding Window Dataset]
        P -->|Huấn luyện v2| Q(Pipeline v2)
        Q -->|Đánh giá| C
        Q -->|Đăng ký model| G
        G -->|Gán alias| R[models:/anomaly-detector@staging]
        
        %% Gate & Swap
        R -->|Cổng phê duyệt| S{Người dùng duyệt y/N?}
        S -->|Từ chối N| T[Giữ v2 ở staging]
        S -->|Đồng ý y| U[Thăng cấp v2 lên @production]
        U -->|Gọi POST /reload| J3
        J3 -->|Nạp model mới| I
    end

    %% Giám sát sau triển khai
    subgraph Post-Deployment Monitoring
        I -->|Serve v2| V[post_deploy_monitor - 24 chu kỳ]
        D -->|Dữ liệu thực tế| V
        V --> W{Precision < 0.65?}
        W -->|Không| X[v2 Hoạt động ổn định]
        W -->|Có| Y[Tự động Rollback]
        Y -->|Set alias production về v1| G
        Y -->|Set alias archived cho v2| G
        Y -->|Gọi POST /reload| J3
    end

    %% Đẩy metrics
    L -->|Đẩy drift score| Z[(Prometheus Pushgateway)]
    O -->|Đẩy event & version| Z
    Z -->|Scraping| K
    K -->|Visualizing| AA[Grafana Dashboard port 3000]
```

---

## 3. Hướng Dẫn Từng Bước Chạy Hệ Thống

Hãy mở terminal tại thư mục dự án của bạn (`d:\Xbrain_BT\aiops-ngothanhtuan\w3\lab-individual\lab-mlops-lifecycle-20260618\lab-mlops-lifecycle\data-pack`) và thực hiện theo các bước sau:

### Bước 1: Khởi động Docker Stack
Chạy script khởi động để chạy MLflow, Postgres, Prometheus, Pushgateway và Grafana:
```bash
bash scripts/start_stack.sh
```
*Đợi khoảng 20-30 giây để các container khởi động hoàn toàn và tạo cơ sở dữ liệu.*
*Bạn có thể truy cập các địa chỉ sau trên trình duyệt để kiểm tra:*
* *MLflow UI:* http://localhost:5000
* *Grafana Dashboard:* http://localhost:3000 (Xem dashboard "AIOps MLOps Lifecycle")
* *Prometheus:* http://localhost:9090

### Bước 2: Thiết lập môi trường ảo Python và cài thư viện
1. Tạo môi trường ảo với Python 3.11 (để đảm bảo tương thích hoàn toàn bánh xe wheel của MLflow 2.13.2 trên Windows):
   ```bash
   uv venv --python 3.11 --clear
   ```
2. Kích hoạt môi trường ảo:
   * **PowerShell:** `.venv\Scripts\Activate.ps1`
   * **Cmd:** `.venv\Scripts\activate.bat`
   * **Git Bash:** `source .venv/Scripts/activate`
3. Cài đặt các thư viện phụ thuộc:
   ```bash
   uv pip install "mlflow==2.13.2" "evidently==0.4.40" scikit-learn pandas numpy fastapi uvicorn prometheus_client requests
   ```

### Bước 3: Sinh dữ liệu kiểm thử
Chạy script để sinh các file dữ liệu CSV cần thiết trong thư mục `data/` (`baseline.csv`, `drifted.csv`, `holdout.csv`, `post_deploy_eval.csv`):
```bash
uv run python data/generate_data.py
```

### Bước 4: Huấn luyện và Đăng ký Mô hình v1
Thiết lập địa chỉ MLflow tracking và chạy script huấn luyện mô hình v1 trên dữ liệu baseline:
```bash
# Thiết lập biến môi trường (Windows PowerShell)
$env:MLFLOW_TRACKING_URI="http://localhost:5000"

# Hoặc trên Git Bash / Linux:
# export MLFLOW_TRACKING_URI=http://localhost:5000

# Chạy huấn luyện
uv run python ngothanhtuan/pipeline.py --data data/baseline.csv
```
*Mô hình v1 sẽ được huấn luyện, log các chỉ số vào MLflow và tự động đăng ký với alias `production`.*

### Bước 5: Khởi chạy Server Phục vụ Mô hình (FastAPI)
Mở một **Terminal mới**, kích hoạt lại môi trường ảo, thiết lập biến môi trường và chạy server:
```bash
# Kích hoạt môi trường ảo và thiết lập biến môi trường (PowerShell)
.venv\Scripts\Activate.ps1
$env:MLFLOW_TRACKING_URI="http://localhost:5000"

# Khởi chạy server
uv run python ngothanhtuan/serve.py
```
*Server sẽ chạy tại cổng 8000. Bạn có thể kiểm tra phiên bản đang chạy bằng cách gõ lệnh sau ở terminal cũ:*
```bash
curl http://localhost:8000/health/active-version
```

### Bước 6: Chạy Thử Nghiệm Kịch Bản Stress Test & Tự Động Huấn Luyện Lại (Retrain + Rollback)
Quay lại **Terminal đầu tiên** (đảm bảo đã thiết lập `MLFLOW_TRACKING_URI=http://localhost:5000`) và chạy script điều phối chính:

```bash
uv run python ngothanhtuan/retrain.py \
    --reference data/baseline.csv \
    --current data/drifted.csv \
    --holdout data/holdout.csv \
    --post-deploy-eval data/post_deploy_eval.csv \
    --auto-approve
```

#### Quá trình diễn ra tự động như sau:
1. **Phát hiện Drift (Stress 1):** Chạy kiểm tra kết hợp (`combined` mode). Phát hiện dữ liệu bị lệch (drift score = 0.67 > 0.15) và hiệu năng bị giảm sút.
2. **Chọn dữ liệu huấn luyện lại (Stress 2):** Kết hợp baseline + drifted (sliding window) để huấn luyện v2, đánh giá hiệu năng trên `holdout.csv` và in ra kết quả:
   `Holdout validation — v2 precision: X.XXXX recall: X.XXXX` (đảm bảo độ chính xác $\ge$ v1).
3. **Đăng ký mô hình v2:** Lưu vào MLflow Registry dưới alias `staging`.
4. **Phê duyệt tự động:** Do truyền tham số `--auto-approve`, hệ thống tự động thăng cấp v2 lên `production` và hạ cấp v1.
5. **Nạp lại mô hình:** Gửi request `/reload` để `serve.py` nạp nóng mô hình v2.
6. **Giám sát sau triển khai và Tự động Rollback (Stress 3):** Giám sát hiệu năng của v2 trên tập dữ liệu `post_deploy_eval.csv` qua 24 chu kỳ. Khi precision rơi xuống dưới 0.65, hệ thống sẽ kích hoạt **Auto-rollback**:
   * Hạ cấp v2 xuống `@archived`.
   * Khôi phục v1 lên `@production`.
   * Gọi reload FastAPI về v1.
   * Ghi log sự kiện vào file `outputs/audit_log.jsonl`.
   * In ra màn hình dòng chữ: `Rollback complete. v1 restored to @production. v2 → @archived`.

Bạn có thể kiểm tra file `outputs/audit_log.jsonl` để xem toàn bộ lịch sử các sự kiện và lý do rollback.

---
*Chúc bạn chạy thực nghiệm thành công! Nếu có bất kỳ câu hỏi nào, vui lòng phản hồi cho tôi biết.*
