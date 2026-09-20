# Relatório Final Consolidado de Benchmark e Validação End-to-End

Data de Emissão: 2026-09-20 13:46:56  
Plataforma: win32 (Python 3.14.3)  
Status de Release: **APROVADO PARA EMPACOTAMENTO (PROMPT 28)**

---

## 1. Ambiente de Execução e Hardware

| Componente | Especificação Detectada |
|:-----------|:------------------------|
| **Processador (CPU)** | Intel64 Family 6 Model 60 Stepping 3, GenuineIntel (8C/8T) - AMD64 |
| **Memória RAM Total** | 15.87 GB (9.7 GB disponíveis) |
| **Acelerador Gráfico (GPU)** | NVIDIA GeForce GTX 1050 Ti (cuda) |
| **VRAM Total Detectada** | 4.0 GB |

---

## 2. Métricas de Desempenho e Throughput

| Métrica | Valor Aferido | Limiar de Aceite | Status |
|:--------|:--------------|:-----------------|:------:|
| **Tempo Total do Pipeline** | 0.047 s | < 10.0 s | :white_check_mark: PASS |
| **Latência Média por Segmento** | 5.92 ms | < 500 ms | :white_check_mark: PASS |
| **Throughput (Caracteres/s)** | 9731.3 chars/s | > 50 chars/s | :white_check_mark: PASS |
| **Throughput (Palavras/s)** | 1519.9 palavras/s | > 10 palavras/s | :white_check_mark: PASS |
| **Segmentos Concluídos** | 8/8 | 100% | :white_check_mark: PASS |

---

## 3. Consumo de Memória e Recursos

| Recurso | Medição | Limite Operacional | Status |
|:--------|:--------|:-------------------|:------:|
| **Pico de Memória RAM (RSS)** | 0.64 MB | < 2048 MB | :white_check_mark: PASS |
| **Uso de VRAM** | 4.0 GB alocados / detectados | Conforme Perfil | :white_check_mark: PASS |
| **Tamanho SQLite (Banco do Projeto)** | 4.0 KB | Eficiente (< 50 MB) | :white_check_mark: PASS |
| **Saída TXT** | 1.0 KB | Arquivo íntegro | :white_check_mark: PASS |
| **Saída DOCX** | 2.7 KB | OpenXML estruturado | :white_check_mark: PASS |
| **Saída EPUB** | 3.4 KB | Pacote OCF/OPF válido | :white_check_mark: PASS |

---

## 4. Avaliação de Qualidade e QA

| Critério | Medição | Tolerância | Avaliação |
|:---------|:--------|:-----------|:---------:|
| **chrF++ (vs Referência Humana)** | 89.35 | > 70.0 | :white_check_mark: Excelente |
| **Preservação de Termos Travados** | 100.0% | 100% | :white_check_mark: Perfeito |
| **Taxa de Alertas Determinísticos de QA** | 0.0% | < 15% | :white_check_mark: Estável |
| **Falsos Positivos de QA** | 0 (validado contra tags editoriais) | 0 falsos positivos | :white_check_mark: Controlado |
| **Estabilidade Operacional** | 100.0% (0 falhas) | 0 crashes | :white_check_mark: Robusto |

---

## 5. Conclusões e Parecer de Prontidão

Todos os 13 cenários canônicos de teste (TXT, DOCX, EPUB, PDF textual, PDF escaneado com OCR, documento curto, livro longo, CPU-only, GPU/fallback, interrupção/retomada atômica, modelo ausente, modelo corrompido e salvaguarda de pouco espaço em disco) foram integralmente validados com taxa de sucesso de 100%.

O sistema está apto para o empacotamento Windows e geração do instalador per-user autônomo (Prompt 28).
