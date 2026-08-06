# run_llm_model.ps1

llama-server -m "C:\Users\Dreydeveloper\.cache\llama.cpp\llm\Qwen3.5-2B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf" `
  --mmproj "C:\Users\Dreydeveloper\.cache\llama.cpp\vision\mmproj-Qwen3.5-2B-Uncensored-HauhauCS-Aggressive-f16.gguf" `
  -ngl 99 -c 16384 -ctk q8_0 -ctv q8_0 --image-max-tokens 1024 -t 6 `
  --host 0.0.0.0 --port 8080 -fit off `
  --chat-template-file "C:\Users\Dreydeveloper\Desktop\Jet_Files\AI_Files\llama_cpp\jinja-templates\Qwen3.5_2B_adjusted.jinja" `
  -a "qwen3.5-uncensored:2b" `
  --tags llm
