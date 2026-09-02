import os
import glob
import time
import base64
from openai import OpenAI

# Inicializa o cliente OpenAI
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def analisar_imagens_pasta(pasta):
    caminhos_imagens = sorted(glob.glob(os.path.join(pasta, "*.*")))
    if not caminhos_imagens:
        print(f"Nenhuma imagem encontrada na pasta '{pasta}'.")
        return None

    print(f"Enviando {len(caminhos_imagens)} imagens da pasta '{pasta}' para análise com OpenAI...")
    
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
        
        base64_img = base64.b64encode(dados_img).decode("utf-8")
        
        # Força o MIME type correto para JPEG
        content_messages.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_img}"
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
                
                nome_arquivo = f"tabela_{pasta}.md"
                with open(nome_arquivo, "w", encoding="utf-8") as f:
                    f.write(resultado)
                print(f"Tabela salva em '{nome_arquivo}'")
            
            time.sleep(2)
        else:
            print(f"Pasta '{pasta}' não encontrada.")