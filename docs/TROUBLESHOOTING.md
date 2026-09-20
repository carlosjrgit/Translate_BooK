# Solução de Problemas e Perguntas Frequentes (FAQ) — Translate_BooK

Este guia ajuda a resolver os problemas mais comuns encontrados durante a instalação, execução ou tradução com o **Translate_BooK**.

---

## 1. Primeiros Passos e Diagnóstico Rápido

Antes de investigar problemas específicos, você pode gerar um relatório automático de saúde do sistema via linha de comando:

```bash
book-translator --diagnostics
# ou
python -m book_translator.cli --diagnostics
```

Este comando verifica:
- Versão do Python e bibliotecas essenciais;
- Presença de GPU NVIDIA e suporte a CUDA;
- Disponibilidade do Tesseract OCR;
- Modelos instalados localmente e integridade de arquivos;
- Permissões nos diretórios de projetos e modelos.

---

## 2. Perguntas Frequentes e Resoluções

### 2.1 "Modelo de IA não instalado" ao iniciar um projeto
- **Causa**: O Translate_BooK não embute pesos neurais pesados no instalador inicial para permitir downloads rápidos e instalação leve.
- **Solução**:
  1. Abra o aplicativo.
  2. Vá em **Configurações** > **Gerenciador de Modelos**.
  3. Escolha o modelo desejado (recomendado: `madlad400-7b-mt-ct2-int8` para computadores com 8GB+ RAM, ou `madlad400-3b-mt-ct2-int8` para máquinas mais modestas).
  4. Clique em **Baixar**. O download utiliza conexão segura HTTPS e valida a integridade com SHA-256 automaticamente.

---

### 2.2 Erro "CUDA Out of Memory" (VRAM Insuficiente)
- **Causa**: Sua placa de vídeo não tem memória VRAM suficiente para manter o modelo selecionado carregado simultaneamente com outros aplicativos (como navegadores ou jogos).
- **Solução**:
  1. Vá em **Configurações** > **Hardware**.
  2. Em "Dispositivo", selecione **CPU** (ou altere o perfil para **Economy** com o modelo 3B).
  3. No modo CPU, o Translate_BooK utiliza sua memória RAM principal, que geralmente é muito maior que a VRAM da GPU, eliminando completamente falhas de memória.

---

### 2.3 "Tesseract OCR não encontrado" ao carregar PDF escaneado
- **Causa**: O módulo de OCR é opcional e requer que o motor Tesseract esteja instalado no sistema.
- **Solução**:
  1. No Windows, baixe e instale o instalador do Tesseract: [UB-Mannheim Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki).
  2. Certifique-se de marcar o suporte a "Portuguese" e "English" nos pacotes de linguagem durante a instalação.
  3. Caso tenha instalado em um caminho customizado, adicione o caminho ao seu `PATH` do Windows ou configure o caminho no Translate_BooK em **Configurações** > **OCR**.

---

### 2.4 Interrupção de Energia ou Fechamento Inesperado
- **O que acontece**: O Translate_BooK grava cada sentença traduzida e aprovada imediatamente no banco de dados SQLite local em modo WAL (*Write-Ahead Logging*).
- **Como retomar**:
  1. Reabra o Translate_BooK.
  2. Clique em **Abrir Projeto** e selecione a pasta do seu livro.
  3. Clique em **Retomar Tradução**. O pipeline recomeçará exatamente do último parágrafo que não foi concluído, sem reprocessar ou cobrar o que já foi traduzido.

---

### 2.5 Espaço em Disco Insuficiente
- **Causa**: O sistema verifica proativamente se há pelo menos 2 GB de espaço livre na unidade antes de iniciar uma nova tradução ou baixar um modelo.
- **Solução**:
  - Libere espaço na unidade do sistema (geralmente `C:\`).
  - Alternativamente, você pode mover a pasta de modelos para outro disco (ex: `D:\Modelos_IA`) através de **Configurações** > **Diretório de Modelos**.

---

### 2.6 Onde Ficam Armazenados Meus Projetos e Logs?
- **Projetos do Usuário**:
  - Windows: `%APPDATA%\Translate_BooK\projects\`
  - *(Estes arquivos nunca são apagados ao desinstalar ou atualizar o programa)*.
- **Modelos e Pesos**:
  - Windows: `%LOCALAPPDATA%\Translate_BooK\models\`
- **Logs de Diagnóstico**:
  - Windows: `%LOCALAPPDATA%\Translate_BooK\logs\translate_book.log`
