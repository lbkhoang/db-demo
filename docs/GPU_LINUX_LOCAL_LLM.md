# Môi trường GPU / Linux cho suy luận LLM local

Tài liệu này giải thích stack cần thiết để chạy Large Language Model (LLM) local bằng GPU NVIDIA:

**Linux → Docker → NVIDIA Driver → CUDA → NVIDIA Container Toolkit → Ollama/llama.cpp/PyTorch → Model**

Mục tiêu là để model chạy trên GPU của máy, thay vì chỉ chạy trên CPU. Cách này giảm thời gian sinh token và giúp chạy model có nhiều tham số hơn.

## 1. Các thành phần trong hệ thống

### Linux

Linux là hệ điều hành nền cho máy chạy AI server. Nó phù hợp vì:

- Driver NVIDIA, CUDA và Docker được hỗ trợ trực tiếp.
- Có thể chạy headless qua SSH, không cần giao diện desktop.
- Dễ tự động hóa bằng shell script và systemd.
- Nhiều framework AI được kiểm thử đầu tiên trên Linux.

Ubuntu LTS thường được chọn cho máy demo hoặc production vì tài liệu và package ổn định.

### Docker

Docker đóng gói runtime của ứng dụng vào container. Container có thể chứa:

- Ollama hoặc inference server.
- Python và thư viện RAG/agent.
- Phiên bản CUDA runtime phù hợp.
- Biến môi trường và cấu hình model.

Docker giúp môi trường demo có thể tái tạo trên máy khác. Docker không tự cung cấp GPU; nó cần NVIDIA Container Toolkit để ánh xạ GPU từ host vào container.

### NVIDIA GPU

GPU có hàng nghìn CUDA core và khả năng xử lý song song. Inference LLM gồm nhiều phép nhân ma trận nên GPU thường nhanh hơn CPU rất nhiều.

Ba thông số cần xem:

1. **VRAM capacity**: model và KV cache có vừa trong VRAM không.
2. **Memory bandwidth**: tốc độ đọc trọng số model trong mỗi token.
3. **Compute throughput**: năng lực tính toán tensor/CUDA core.

Với LLM local, VRAM thường là giới hạn đầu tiên. Một GPU nhanh nhưng chỉ có 8 GB VRAM có thể kém hữu ích hơn GPU chậm hơn nhưng có 16 GB nếu model phải tràn sang RAM.

### CUDA

CUDA là nền tảng của NVIDIA cho phép phần mềm gọi GPU. Trong inference, CUDA cung cấp:

- Driver API và runtime để giao tiếp với GPU.
- Kernel cho phép chạy phép tính song song.
- Thư viện tối ưu như cuBLAS, cuDNN và TensorRT.

Cần phân biệt **NVIDIA driver trên host** và **CUDA runtime trong container**. Driver phải được cài trên Linux host; container thường chứa CUDA user-space libraries tương thích.

### NVIDIA Container Toolkit

NVIDIA Container Toolkit là cầu nối giữa Docker và GPU NVIDIA. Nó cho phép container nhìn thấy:

- `/dev/nvidia*`
- CUDA libraries cần thiết
- GPU được chỉ định qua `--gpus all` hoặc Docker Compose

Luồng cài đặt tổng quát trên Ubuntu/Debian:

```bash
# Kiểm tra driver trên host
nvidia-smi

# Cài toolkit (theo repository chính thức của NVIDIA)
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Cấu hình Docker dùng NVIDIA runtime
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Kiểm tra container nhìn thấy GPU
sudo docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Tên CUDA image phải được chọn theo driver đang cài. Không nên tùy ý dùng image CUDA mới hơn khả năng hỗ trợ của driver host.

### Ollama hoặc inference server

Ollama là lớp chạy model và cung cấp API HTTP. Ứng dụng RAG/agent gọi API này để chat hoặc tạo embedding.

Một flow điển hình:

```text
Client/CLI
   ↓ HTTP
Ollama container
   ↓ CUDA
NVIDIA GPU
   ↓ VRAM
Quantized LLM model
```

Với hệ thống cần throughput cao hơn, có thể cân nhắc llama.cpp server, vLLM hoặc TensorRT-LLM. Ollama phù hợp cho demo, máy đơn và vận hành đơn giản.

## 2. Quyền truy cập GPU trong Docker Compose

Ví dụ tối giản:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

volumes:
  ollama:
```

Kiểm tra sau khi khởi động:

```bash
docker compose up -d ollama
docker compose exec ollama nvidia-smi
curl http://localhost:11434/api/tags
```

Nếu `nvidia-smi` chạy được trên host nhưng không chạy được trong container, thường cần kiểm tra NVIDIA Container Toolkit, Docker daemon và phiên bản driver.

## 3. RAM hệ thống và VRAM GPU

### DDR4 và DDR5

DDR4/DDR5 là RAM hệ thống. Khi model không vừa VRAM, một phần trọng số hoặc KV cache có thể bị đẩy sang RAM qua PCIe. Khi đó tốc độ thường giảm mạnh.

| Loại RAM | Ví dụ tốc độ | Băng thông lý thuyết mỗi kênh | Vai trò trong LLM |
|---|---:|---:|---|
| DDR4-3200 | 3.200 MT/s | khoảng 25,6 GB/s | Đủ cho CPU inference nhỏ; giá thấp |
| DDR5-4800 | 4.800 MT/s | khoảng 38,4 GB/s | Tốt hơn khi CPU phải đọc nhiều dữ liệu |
| DDR5-5600 | 5.600 MT/s | khoảng 44,8 GB/s | Băng thông cao hơn, phù hợp máy mới |

DDR5 không làm GPU nhanh gấp đôi. Nếu toàn bộ model nằm trong VRAM, tốc độ DDR4/DDR5 chỉ ảnh hưởng ít. DDR5 có lợi khi chạy CPU inference, load model, embedding hoặc khi model bị offload sang RAM.

### GDDR6 và GDDR7

GDDR6/GDDR7 là bộ nhớ trên GPU, thường gọi là VRAM. Nó có băng thông cao hơn RAM hệ thống rất nhiều và nằm gần GPU.

| Bộ nhớ GPU | Đặc điểm | Ảnh hưởng thực tế |
|---|---|---|
| GDDR6 | Phổ biến ở nhiều GPU, băng thông tốt | Chạy tốt model quantized vừa VRAM |
| GDDR6X | Tốc độ cao hơn GDDR6 nhưng nóng hơn | Tăng bandwidth, cần tản nhiệt tốt |
| GDDR7 | Thế hệ mới, bandwidth và hiệu suất điện tốt hơn | Có lợi cho model lớn và tốc độ sinh token |

Trong câu hỏi này, “D4/D5/D7” nên hiểu là **DDR4/DDR5 của RAM hệ thống** và **GDDR7 của VRAM GPU**. DDR5 và GDDR7 không phải hai cấp RAM có thể thay thế trực tiếp cho nhau.

## 4. Phần cứng nào quan trọng nhất trong AI?

| Thành phần | Mức ảnh hưởng tới LLM inference | Khi nào quan trọng |
|---|---|---|
| VRAM dung lượng | Rất cao | Quyết định model có nằm hoàn toàn trên GPU không |
| GPU memory bandwidth | Rất cao | Ảnh hưởng tốc độ đọc trọng số và sinh token |
| Tensor/CUDA compute | Cao | Quan trọng với prompt dài, batch lớn và model nhiều phép tính |
| CPU | Trung bình | Tokenizer, orchestration, offload và xử lý dữ liệu |
| RAM hệ thống | Trung bình đến cao | CPU inference, load model, embedding và offload |
| SSD NVMe | Trung bình | Tốc độ khởi động và load model; ít ảnh hưởng token/sau khi đã load |
| PCIe | Trung bình | Quan trọng khi model/KV cache phải trao đổi giữa RAM và VRAM |
| Mạng | Thấp với model local | Chỉ ảnh hưởng khi model hoặc database nằm trên máy khác |

Thứ tự ưu tiên thực tế cho một máy local thường là:

```text
VRAM đủ chứa model
→ GPU bandwidth/compute
→ RAM hệ thống
→ CPU
→ SSD
```

## 5. Bảng tốc độ sinh token tham khảo

Các số dưới đây chỉ là khoảng tham khảo cho model 7B–8B quantized, batch nhỏ, context vừa và một request đơn. Đây không phải benchmark cố định. Model, quantization, context length, nhiệt độ GPU, driver và phần mềm inference đều có thể làm kết quả khác đi.

| Cấu hình chạy model | VRAM/RAM khả dụng | Tốc độ sinh token tham khảo | Nhận xét |
|---|---:|---:|---|
| CPU laptop, DDR4, model Q4 | 16–32 GB RAM | 2–8 token/s | Chạy được nhưng phản hồi chậm |
| CPU desktop, DDR5, model Q4 | 32–64 GB RAM | 5–15 token/s | DDR5 giúp bandwidth CPU tốt hơn |
| GPU 8 GB GDDR6, model vừa VRAM | 8 GB VRAM | 20–60 token/s | Nhanh hơn CPU rõ rệt |
| GPU 12 GB GDDR6/GDDR6X | 12 GB VRAM | 30–90 token/s | Có thêm không gian cho context |
| GPU 16 GB GDDR7, model vừa VRAM | 16 GB VRAM | 40–120 token/s | Phù hợp model 7B–14B quantized tùy context |
| GPU 24 GB GDDR6/GDDR7 | 24 GB VRAM | 60–180+ token/s | Tốt cho model lớn hơn hoặc batch nhiều |
| GPU bị tràn sang DDR4/DDR5 | VRAM không đủ | Có thể giảm còn 1–20 token/s | PCIe/RAM trở thành nút thắt |

Ví dụ với GPU 16 GB GDDR7 như máy demo: nên ưu tiên model quantized nằm trọn trong 16 GB VRAM. Khi model vượt dung lượng này, việc dùng thêm DDR5 không bù được độ trễ trao đổi qua PCIe.

## 6. Cách đo trên máy thật

Không nên dùng bảng ước lượng để cam kết hiệu năng. Hãy đo cùng một model, cùng quantization và cùng prompt:

```bash
# Theo dõi GPU trong lúc inference
watch -n 1 nvidia-smi

# Gọi model qua Ollama
curl http://localhost:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3:4b","prompt":"Explain RAG in three sentences","stream":false}'
```

Khi đánh giá, ghi lại:

- `prompt_eval_duration`: thời gian đọc prompt.
- `eval_duration`: thời gian sinh output.
- `eval_count`: số token output.
- `eval_count / eval_duration`: token/giây.
- VRAM đã dùng và nhiệt độ GPU.

## 7. Checklist triển khai

- [ ] Linux kernel và NVIDIA driver được cài đúng.
- [ ] `nvidia-smi` chạy được trên host.
- [ ] Docker Engine hoạt động.
- [ ] NVIDIA Container Toolkit đã cấu hình Docker.
- [ ] Container CUDA chạy được `nvidia-smi`.
- [ ] Ollama nhìn thấy GPU và model đã được pull.
- [ ] Model quantized vừa VRAM với context dự kiến.
- [ ] Có benchmark token/s trên chính máy triển khai.
- [ ] Có giới hạn context và số request để tránh hết VRAM.

Tham khảo cài đặt NVIDIA Container Toolkit: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
