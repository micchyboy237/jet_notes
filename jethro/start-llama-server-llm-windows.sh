llama-server `
  --model "C:\Users\druiv\.cache\llama.cpp\Ministral-3b-instruct.Q4_K_M.gguf" `
  -c 8192 `
  -ngl 999 `
  --flash-attn on `
  -ub 512 `
  -b 1024 `
  --parallel 1 `
  --temp 0.1 `
  --top-p 0.95 `
  --min-p 0.05 `
  --repeat-penalty 1.1 `
  --cache-type-k q8_0 `
  --cache-type-v q8_0 `
  --host 0.0.0.0 `
  --port 8080


llama-server `
  --model C:\Users\druiv\.cache\llama.cpp\Ministral-3b-instruct.Q4_K_M.gguf `
  --ctx-size 2048 `
  --n-gpu-layers all `
  --flash-attn on `
  --batch-size 1024 `
  --ubatch-size 512 `
  --mlock `
  --host 0.0.0.0 `
  --port 8080 `
  --no-mmap `
  --cont-batching `
  --cache-type-k q8_0 `
  --cache-type-v q8_0 `
  --jinja


llama-server `
  --model C:\Users\druiv\.cache\llama.cpp\Ministral-3b-instruct.Q4_K_M.gguf `
  --chat-template-file C:\Users\druiv\Desktop\Jet_Files\Jet_Windows_Workspace\jinja_templates\ministral-3b-instruct.jinja `
  --jinja `
  --ctx-size 4096 `
  --n-gpu-layers all `
  --flash-attn on `
  --batch-size 1024 `
  --ubatch-size 512 `
  --mlock `
  --host 0.0.0.0 `
  --port 8080 `
  --no-mmap `
  --cont-batching `
  --cache-type-k q8_0 `
  --cache-type-v q8_0
