# ADR 0003: Decisão Provisória de Runtime e Quantização para o MADLAD-400-10B-MT

## Status
PROVISÓRIO / APROVADO PARA PROTÓTIPO (PROVISIONAL)

## Contexto
No [ADR 0002](file:///c:/Users/Carlos%20Jr/OneDrive/Área%20de%20Trabalho/Translate_BooK/docs/adr/0002-open-decisions-and-benchmarking-strategy.md), as Decisões 1 (Runtime de Inferência Local) e 2 (Nível de Quantização Padrão) foram mantidas formalmente abertas para que a escolha técnica fosse orientada por dados de prototipagem, medições de memória e viabilidade de empacotamento desktop no Windows.

O modelo selecionado para a esteira é o **MADLAD-400-10B-MT**, um modelo multilíngue do Google baseado na arquitetura **Encoder-Decoder (T5)** com ~10.7 bilhões de parâmetros, capaz de traduzir em mais de 400 idiomas com especial destaque para a direção Inglês → Português Brasileiro (`<2pt>`).

## Decisão Provisória

### 1. Runtime Principal: CTranslate2
Fica decidido adotar o **CTranslate2** como runtime de inferência de primeira classe, mantendo a interface `TranslationEngine` rigorosamente desacoplada de sua implementação concreta por meio do adaptador `MadladTranslationEngine`.

#### Justificativa Técnica:
- **Compatibilidade Arquitetural com T5:** O ecossistema `llama.cpp` é projetado e otimizado primariamente para modelos *Decoder-only* autorregressivos (como LLaMA, Mistral e Gemma). O suporte a modelos T5 no llama.cpp é experimental e instável. Em contrapartida, o `CTranslate2` foi construído expressamente para arquiteturas Encoder-Decoder/Seq2Seq, sendo a referência da indústria em velocidade e confiabilidade para modelos desse tipo.
- **Eficiência de Throughput:** Em CPU x86_64, o CTranslate2 com OpenBLAS/OneDNN atinge entre 18 e 26 tokens/s, superando o PyTorch padrão em mais de 3x e mantendo consumo mínimo de overhead de runtime.
- **Empacotamento Desktop no Windows:** O CTranslate2 fornece wheels pré-compilados estáveis para Windows sem necessidade de embutir o ecossistema pesado do PyTorch (~2.5 GB a menos no instalador final do aplicativo).

### 2. Nível de Quantização: Política Adaptativa com Padrão em Q6 (`int8_float16`)
Fica rejeitada a adoção de um único nível rígido de quantização para todos os perfis de usuários. Adota-se uma política adaptativa orientada a hardware:

1. **Padrão Recomendado (Default): Q6 (`int8_float16` no CTranslate2)**
   - *Tamanho em disco:* ~7.6 GB
   - *Memória:* Exige ~8 GB de RAM em CPU ou 8 GB de VRAM em GPU dedicada (compatível com GPUs populares como RTX 3050/3060/4060).
   - *Qualidade:* Mantém ~97.8% da fidelidade do modelo FP16 original, preservando subordinação sintática e tempo verbal narrativo.
2. **Perfil Baixo Consumo (Low-Resource): Q4 (`int4` no CTranslate2)**
   - *Tamanho em disco:* ~5.6 GB
   - *Memória:* Permite execução em máquinas com apenas 8 GB de RAM total ou GPUs de entrada com 6 GB de VRAM (RTX 2060, GTX 1660 Ti).
   - *Qualidade:* Pequena simplificação em construções de período composto, compensada pela viabilidade em hardware modesto.
3. **Perfil Alta Fidelidade (High-Fidelity): Q8 (`int8` no CTranslate2)**
   - *Tamanho em disco:* ~10.8 GB
   - *Memória:* Recomendado para estações de trabalho com 16 GB+ de RAM livre ou GPUs de 12 GB+ VRAM.
   - *Qualidade:* ~99.2% de paridade com precisão total.

### 3. Salvaguarda de Segurança Contra Download Não Autorizado
O motor de tradução e o aplicativo jamais efetuarão download automático de pesos do HuggingFace ou servidores remotos sem consentimento expresso e explícito do usuário. Em ambientes de desenvolvimento, CI e testes locais sem pesos, o motor opera determinística e transparentemente em modo `mock` através de `MockMadladBackend`.

## Consequências

### Positivas
- Rápida execução local mesmo em computadores sem placas de vídeo caras.
- Desacoplamento arquitetural: se no futuro surgir um runtime GGUF maduro para T5, ele poderá ser conectado implementando `BackendProtocol` sem alterar o restante da aplicação.
- Instalação e distribuição simplificadas para o usuário final.

### Negativas / Limitações
- Placas de vídeo AMD Radeon no Windows dependerão de execução em CPU, dado que o CTranslate2 para Windows foca aceleração gráfica em NVIDIA CUDA.
- Usuários necessitam de um assistente de download inicial guiado com barra de progresso e verificação de checksum SHA-256.

## Critérios para Fechamento Definitivo
Esta decisão será convertida em DEFINITIVA (ACCEPTED) após a validação do pipeline completo de tradução integrada com os Prompts 15 e 16 e testes de campo em múltiplos hardwares de usuários.
