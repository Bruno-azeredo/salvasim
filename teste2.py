import os
import glob
import time
from datetime import datetime
from openai import OpenAI

# Inicializa o cliente OpenAI (utiliza a variável de ambiente OPENAI_API_KEY)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def analisar_imagens_pasta(pasta):
    caminhos_imagens = sorted(glob.glob(os.path.join(pasta, "*.*")))
    if not caminhos_imagens:
        print(f"Nenhuma imagem encontrada na pasta '{pasta}'.")
        return []

    print(f"Enviando {len(caminhos_imagens)} imagens da pasta '{pasta}' para análise com OpenAI...")
    
    # Prepara as imagens no formato aceito pelo modelo GPT-4o (via URL de dados Base64 ou arquivos)
    # Como a API da OpenAI suporta URLs/Data URIs para imagens, vamos convertê-las em base64:
    import base64
    
    content_messages = [
        {
            "type": "text",
            "text": (
                "Analise todas estas páginas de encarte de supermercado fornecidas. "
                "Extraia e liste todos os produtos ofertados em formato de tabela Markdown estruturada com as seguintes colunas exatas: "
                "Mercado, Nome do Produto, Preço e Data Final da Oferta. "
                "Se a data final não estiver visível em nenhuma página, coloque 'Não informada'. "
                "Retorne apenas a tabela Markdown limpa."
            )
        }
    ]

    for caminho in caminhos_imagens:
        with open(caminho, "rb") as f:
            dados_img = f.read()
        ext = caminho.split(".")[-1].lower()
        mime_type = "image/webp" if ext == "webp" else "jpeg" if ext in ["jpg", "jpeg"] else "png"
        base64_img = base64.b64encode(dados_img).decode("utf-8")
        
        content_messages.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{base64_img}"
            }
        })

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": content_messages
                }
            ],
            max_tokens=4096
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Erro ao processar as imagens com a OpenAI: {e}")
        return None

if __name__ == "__main__":
    pastas = ["encarte_assai_completo", "encarte_extra_completo"]
    
    for pasta in pastas:
        if os.path.exists(pasta):
            print(f"\n--- Processando: {pasta} ---")
            resultado = analisar_imagens_pasta(pasta)
            if resultado:
                print(resultado)
                
                # Salva o resultado em um arquivo markdown
                nome_arquivo = f"tabela_{pasta}.md"
                with open(nome_arquivo, "w", encoding="utf-8") as f:
                    f.write(resultado)
                print(f"Tabela salva em '{nome_arquivo}'")
            
            # Delay de segurança entre requisições grandes
            time.sleep(2)
        else:
            print(f"Pasta '{pasta}' não encontrada.")