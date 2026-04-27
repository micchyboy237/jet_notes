# https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512
llama-server \
  --model /Users/jethroestrada/.cache/llama.cpp/llm_models/mistralai_Ministral-3-3B-Instruct-2512-Q4_K_M.gguf \
  --mmproj /Users/jethroestrada/.cache/llama.cpp/llm_models/mmproj-mistralai_Ministral-3-3B-Instruct-2512-f16.gguf \
  --ctx-size 4096 \
  --n-gpu-layers all \
  --flash-attn on \
  --threads 4 \
  --threads-batch 4 \
  --batch-size 1024 \
  --ubatch-size 512 \
  --mlock \
  --host 0.0.0.0 \
  --port 8080 \
  --no-mmap \
  --cont-batching \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --jinja


# JA - EN Translator
llama-server \
  --model /Users/jethroestrada/.cache/llama.cpp/llm_models/mistralai_Ministral-3-3B-Instruct-2512-Q4_K_M.gguf \
  --chat-template-file /Users/jethroestrada/Desktop/External_Projects/Jet_Windows_Workspace/jinja_templates/ministral-3b-instruct.jinja \
  --jinja \
  --ctx-size 4096 \
  --n-gpu-layers all \
  --flash-attn on \
  --threads 4 \
  --threads-batch 4 \
  --batch-size 1024 \
  --ubatch-size 512 \
  --mlock \
  --host 0.0.0.0 \
  --port 8080 \
  --no-mmap \
  --cont-batching \
  --cache-type-k q8_0 \
  --cache-type-v q8_0


# https://huggingface.co/dphn/dolphin-2_6-phi-2
llama-server \
  -m "/Users/jethroestrada/.cache/llama.cpp/llm_models/nsfw/dolphin-2_6-phi-2.Q4_K_M.gguf" \
  -ngl all \
  -c 4096 \
  -b 1024 \
  -ub 512 \
  --threads 4 \
  --threads-batch 4 \
  --cont-batching \
  --cache-prompt \
  -fa auto \
  --mlock \
  --jinja \
  --host 0.0.0.0 \
  --port 8080


# https://huggingface.co/Qwen/Qwen3.5-2B
llama-server \
  -m model.gguf \
  -ngl 20 \
  -c 4096 \
  -b 256 \
  -ub 128 \
  --threads 6 \
  --threads-batch 6 \
  --flash-attn on \
  --cache-type-k q4_0 \
  --cache-type-v q4_0 \
  --cont-batching \
  --host 0.0.0.0 \
  --port 8080


# https://huggingface.co/Qwen/Qwen3.5-2B
llama-server \
  -m "/Users/jethroestrada/.cache/llama.cpp/llm_models/Qwen3.5-0.8B-Q4_K_M.gguf" \
  -ngl all \
  -c 16384 \
  -b 1024 \
  -ub 512 \
  --threads 6 \
  --threads-batch 8 \
  --flash-attn on \
  --cont-batching \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --cache-prompt \
  --mlock \
  --no-mmap \
  --jinja \
  --host 0.0.0.0 \
  --port 8080

# llama-server \
#   -m "/Users/jethroestrada/.cache/llama.cpp/llm_models/Qwen3.5-0.8B-Q4_K_M.gguf" \
#   -ngl 20 \
#   -c 4096 \
#   -b 256 \
#   -ub 128 \
#   --threads 6 \
#   --threads-batch 8 \
#   --flash-attn on \
#   --cache-type-k q4_0 \
#   --cache-type-v q4_0 \
#   --cont-batching \
#   --host 0.0.0.0 \
#   --port 8080
