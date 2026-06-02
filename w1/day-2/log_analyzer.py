import sys
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

def parse_hdfs_timestamp(line):
    """
    Hàm bổ trợ để trích xuất timestamp từ log HDFS.
    Định dạng mẫu: 081109 203615 -> YYMMDD HHMMSS
    Hoặc hỗ trợ định dạng ISO chuẩn nếu bạn test log lạ: 2026-06-02 12:00:00
    """
    # Thử parse định dạng HDFS (ví dụ: 081116 203518)
    hdfs_match = re.match(r'^(\d{6})\s+(\d{6})', line)
    if hdfs_match:
        try:
            date_str, time_str = hdfs_match.groups()
            return datetime.strptime(f"{date_str} {time_str}", "%y%m%d %H%M%S")
        except ValueError:
            pass
            
    # Thử parse định dạng chuẩn ISO nếu có (YYYY-MM-DD HH:MM:SS)
    iso_match = re.match(r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
    if iso_match:
        try:
            return datetime.strptime(iso_match.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
            
    return None

def analyze_log(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' không tồn tại.")
        sys.exit(1)

    # Khởi tạo Drain3 Miner với cấu hình mặc định ẩn danh các số/IP
    config = TemplateMinerConfig()
    miner = TemplateMiner(config=config)

    total_lines = 0
    log_records = [] # Lưu danh sách tuple: (timestamp, template_id, raw_line)
    
    # Đọc file lần 1: Trích xuất timestamp và học template bằng Drain3
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            total_lines += 1
            timestamp = parse_hdfs_timestamp(line)
            
            # Parse log qua Drain3
            result = miner.add_log_message(line)
            template_id = result["cluster_id"]
            
            if timestamp:
                log_records.append((timestamp, template_id, line))

    if not log_records:
        print("Không tìm thấy dữ liệu log hoặc không trích xuất được timestamp hợp lệ.")
        return

    # Xác định mốc thời gian: Giờ cuối cùng (1 giờ gần nhất xuất hiện trong log file)
    max_time = max(rec[0] for rec in log_records)
    one_hour_threshold = max_time - timedelta(hours=1)
    
    # Tính tổng số giờ có trong log file để làm mẫu tính toán trung bình (Tránh chia cho 0)
    min_time = min(rec[0] for rec in log_records)
    total_duration_hours = max((max_time - min_time).total_seconds() / 3600.0, 1.0)
    
    # -----------------------------------------------------------------
    # LOGIC 1 & 2: Thống kê chung & Top-5 Templates (Tính trên TOÀN BỘ FILE)
    # -----------------------------------------------------------------
    all_templates = miner.drain.clusters
    unique_template_count = len(all_templates)
    
    # Tạo map tra cứu thông tin nhanh
    id_to_template_str = {c.cluster_id: c.get_template() for c in all_templates}
    id_to_total_count = {c.cluster_id: c.size for c in all_templates}

    # Sắp xếp tìm Top 5
    sorted_templates = sorted(all_templates, key=lambda x: x.size, reverse=True)
    
    # -----------------------------------------------------------------
    # LOGIC 3 & 4: Phân tách dữ liệu: 1 giờ gần nhất VS Quá khứ (Lịch sử)
    # -----------------------------------------------------------------
    history_counts = defaultdict(int)
    last_hour_counts = defaultdict(int)
    
    for ts, tid, _ in log_records:
        if ts >= one_hour_threshold:
            last_hour_counts[tid] += 1
        else:
            history_counts[tid] += 1

    # Tính số giờ của giai đoạn lịch sử (trước 1 giờ cuối)
    history_duration_hours = max(total_duration_hours - 1.0, 1.0)

    # A. Phát hiện Template tăng đột biến trong 1 giờ gần nhất
    spike_templates = []
    for tid, last_hour_cnt in last_hour_counts.items():
        # Chỉ xét các template đã từng xuất hiện ở quá khứ
        if tid in history_counts:
            avg_history_per_hour = history_counts[tid] / history_duration_hours
            
            # Điều kiện đột biến: Số lượng giờ cuối gấp 3 lần trung bình lịch sử 
            # và số lượng thực tế phát sinh trong giờ cuối phải đủ lớn (ví dụ > 5 dòng) để tránh báo động giả
            if avg_history_per_hour > 0 and last_hour_cnt > (avg_history_per_hour * 3) and last_hour_cnt > 5:
                increase_ratio = (last_hour_cnt - avg_history_per_hour) / avg_history_per_hour * 100
                spike_templates.append((tid, last_hour_cnt, avg_history_per_hour, increase_ratio))
                
    spike_templates.sort(key=lambda x: x[3], reverse=True)

    # B. Phát hiện New Templates bằng TF-IDF + Cosine Similarity
    # Định nghĩa "New Template": Chỉ xuất hiện ở 1 giờ gần nhất, CHƯA TỪNG có trong lịch sử
    strict_new_ids = [tid for tid in last_hour_counts if tid not in history_counts]
    verified_new_templates = []

    if strict_new_ids and history_counts:
        # Gom toàn bộ chuỗi template cũ và mới để vector hóa toán học
        history_ids = list(history_counts.keys())
        all_analyzed_ids = history_ids + strict_new_ids
        
        pure_strings = [id_to_template_str[tid] for tid in all_analyzed_ids]
        
        # Chạy TF-IDF bảo lưu token <*>
        vectorizer = TfidfVectorizer(token_pattern=r'(?u)\b\w+\b|<\*>')
        tfidf_matrix = vectorizer.fit_transform(pure_strings)
        
        # Tính toán ma trận tương đồng cấu trúc
        sim_matrix = cosine_similarity(tfidf_matrix)
        
        # Quét các template mới để đối chiếu ngữ nghĩa với toàn bộ kho lưu trữ lịch sử
        for new_id in strict_new_ids:
            new_idx = all_analyzed_ids.index(new_id)
            
            # Lấy mảng tương đồng của nó với các template lịch sử
            history_indices = [all_analyzed_ids.index(h_id) for h_id in history_ids]
            new_vs_history_sims = sim_matrix[new_idx, history_indices]
            
            max_sim_score = np.max(new_vs_history_sims) if len(new_vs_history_sims) > 0 else 0
            
            # Nếu độ tương đồng cấu trúc < 0.35 -> Khẳng định đây là một định dạng log hoàn toàn "Độc bản" (Anomaly)
            if max_sim_score < 0.35:
                verified_new_templates.append((new_id, last_hour_counts[new_id], max_sim_score))
                
        verified_new_templates.sort(key=lambda x: x[1], reverse=True)
    else:
        # Nếu file quá ngắn (< 1 tiếng), tạm thời coi các template mới sinh ra là new
        for nid in strict_new_ids:
            verified_new_templates.append((nid, last_hour_counts[nid], 0.0))

    # -----------------------------------------------------------------
    # IN KẾT QUẢ RA STDOUT
    # -----------------------------------------------------------------
    print("=======================================================================")
    print("                      HỆ THỐNG PHÂN TÍCH LOG FILE                      ")
    print("=======================================================================")
    print(f"🔹 Tổng số dòng log:           {total_lines:,}")
    print(f"🔹 Số log template unique:     {unique_template_count:,}")
    print(f"🔹 Khoảng thời gian dữ liệu:   {min_time}  -->  {max_time}")
    print(f"🔹 Phạm vi phân tích giờ cuối:  Từ {one_hour_threshold} đến {max_time}")
    print("=======================================================================\n")

    print(f"[TOP-5 LOG TEMPLATES TRÊN TOÀN HỆ THỐNG]")
    for i, cluster in enumerate(sorted_templates[:5], 1):
        percentage = (cluster.size / total_lines) * 100
        print(f" {i}. [ID {cluster.cluster_id}] Xuất hiện: {cluster.size:,} lần ({percentage:.2f}%)")
        print(f"    Cấu trúc: {cluster.get_template()}")
    print()

    print(f"[TEMPLATES TĂNG ĐỘT BIẾN TRONG 1 GIỜ GẦN NHẤT] (So với trung bình lịch sử)")
    if spike_templates:
        for tid, last_cnt, avg_hist, inc_ratio in spike_templates[:5]:
            print(f"[ID {tid}] Giờ cuối: {last_cnt} lần | TB Lịch sử: {avg_hist:.2f} lần/giờ (Tăng +{inc_ratio:.1f}%)")
            print(f"    Cấu trúc: {id_to_template_str[tid]}")
    else:
        print(" -> Không phát hiện template nào có xu hướng tăng đột biến bất thường.")
    print()

    print(f"[NEW TEMPLATES - CẤU TRÚC LẠ MỚI XUẤT HIỆN TRONG GIỜ CUỐI]")
    if verified_new_templates:
        for tid, count, sim in verified_new_templates:
            print(f" [ID {tid}] Xuất hiện: {count} lần trong giờ cuối | Độ trùng khớp lịch sử: {sim*100:.1f}% (Rất thấp)")
            print(f"    Cấu trúc: {id_to_template_str[tid]}")
    else:
        print(" -> Không phát hiện cấu trúc log mới (Anomaly) nào xuất hiện.")
    print("=======================================================================")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Cú pháp chạy chuẩn: python log_analyzer.py <path_to_log_file>")
        sys.exit(1)
        
    log_file_input = sys.argv[1]
    analyze_log(log_file_input)