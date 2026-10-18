import os
import sys

import folium
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("SPTRANS_TOKEN")
BASE_URL = "https://api.olhovivo.sptrans.com.br/v2.1"

BUSCAS_LINHA = ["8610", "875A", "809J", "875C"]


class SPTransAPI:
    def __init__(self, token):
        self.session = requests.Session()
        self.autenticar(token)

    def autenticar(self, token):
        url = f"{BASE_URL}/Login/Autenticar"
        resposta = self.session.post(
            url,
            params={"token": token},
            timeout=30
        )
        resposta.raise_for_status()

        if resposta.json() is not True:
            raise RuntimeError(
                "Falha na autenticação. Verifique o token no arquivo .env."
            )

        print("Autenticação realizada com sucesso.")

    def get(self, endpoint, params=None):
        resposta = self.session.get(
            f"{BASE_URL}/{endpoint}",
            params=params,
            timeout=30
        )
        resposta.raise_for_status()
        return resposta.json()

    def buscar_linhas(self, termo):
        return self.get(
            "Linha/Buscar",
            {"termosBusca": termo}
        )

    def buscar_paradas(self, codigo_linha):
        return self.get(
            "Parada/BuscarParadasPorLinha",
            {"codigoLinha": codigo_linha}
        )

    def buscar_veiculos(self, codigo_linha):
        return self.get(
            "Posicao/Linha",
            {"codigoLinha": codigo_linha}
        )


def escolher_linha(api):
    for termo in BUSCAS_LINHA:
        try:
            linhas = api.buscar_linhas(termo)
        except requests.RequestException as erro:
            print(f"Erro ao buscar linhas com '{termo}': {erro}")
            continue

        linhas = sorted(
            linhas,
            key=lambda linha: (
                linha.get("lt") != termo,
                linha.get("tl") != 10
            )
        )

        for linha in linhas:
            codigo = linha.get("cl")
            if codigo is None:
                continue

            try:
                paradas = api.buscar_paradas(codigo)
                dados = api.buscar_veiculos(codigo)
                veiculos = dados.get("vs", [])

                paradas_validas = [
                    parada for parada in paradas
                    if parada.get("py") is not None
                    and parada.get("px") is not None
                ]

                veiculos_validos = [
                    veiculo for veiculo in veiculos
                    if veiculo.get("py") is not None
                    and veiculo.get("px") is not None
                ]

                if paradas_validas and veiculos_validos:
                    numero = (
                        f"{linha.get('lt', '')}-"
                        f"{linha.get('tl', 10):02d}"
                    )

                    print(f"\nLinha selecionada: {numero}")
                    print(f"Sentido: {linha.get('sl')}")
                    print(f"Terminal principal: {linha.get('tp')}")
                    print(f"Terminal secundário: {linha.get('ts')}")
                    print(f"Paradas encontradas: {len(paradas_validas)}")
                    print(f"Ônibus localizados: {len(veiculos_validos)}")

                    return linha, paradas_validas, veiculos_validos

            except requests.RequestException as erro:
                print(f"Erro na consulta da linha {codigo}: {erro}")

    raise RuntimeError(
        "Nenhuma linha consultada retornou paradas e veículos. "
        "Tente novamente em outro horário ou verifique a API."
    )


def criar_mapa(linha, paradas, veiculos):
    pontos = [
        [parada["py"], parada["px"]]
        for parada in paradas
    ]

    pontos.extend([
        [veiculo["py"], veiculo["px"]]
        for veiculo in veiculos
    ])

    latitude = sum(ponto[0] for ponto in pontos) / len(pontos)
    longitude = sum(ponto[1] for ponto in pontos) / len(pontos)

    mapa = folium.Map(
        location=[latitude, longitude],
        zoom_start=13,
        control_scale=True
    )

    grupo_paradas = folium.FeatureGroup(
        name="Paradas de ônibus",
        show=True
    )

    grupo_veiculos = folium.FeatureGroup(
        name="Ônibus em tempo real",
        show=True
    )

    for parada in paradas:
        nome = parada.get("np", "Parada sem nome")
        endereco = parada.get("ed", "Endereço não informado")
        codigo = parada.get("cp", "N/D")

        folium.Marker(
            location=[parada["py"], parada["px"]],
            tooltip=nome,
            popup=folium.Popup(
                f"<b>Parada:</b> {nome}<br>"
                f"<b>Endereço:</b> {endereco}<br>"
                f"<b>Código:</b> {codigo}",
                max_width=300
            ),
            icon=folium.Icon(
                color="blue",
                icon="info-sign"
            )
        ).add_to(grupo_paradas)

    numero_linha = (
        f"{linha.get('lt', '')}-{linha.get('tl', 10):02d}"
    )

    for veiculo in veiculos:
        prefixo = veiculo.get("p", "Não informado")
        acessivel = "Sim" if veiculo.get("a") else "Não"
        horario = veiculo.get("ta", "Não informado")

        folium.Marker(
            location=[veiculo["py"], veiculo["px"]],
            tooltip=f"Ônibus {prefixo}",
            popup=folium.Popup(
                f"<b>Linha:</b> {numero_linha}<br>"
                f"<b>Prefixo:</b> {prefixo}<br>"
                f"<b>Acessível:</b> {acessivel}<br>"
                f"<b>Horário da posição:</b> {horario}",
                max_width=300
            ),
            icon=folium.Icon(
                color="red",
                icon="bus",
                prefix="fa"
            )
        ).add_to(grupo_veiculos)

    grupo_paradas.add_to(mapa)
    grupo_veiculos.add_to(mapa)

    folium.LayerControl(collapsed=False).add_to(mapa)
    mapa.fit_bounds(pontos)

    arquivo = "mapa_frota.html"
    mapa.save(arquivo)

    print(f"\nMapa salvo em: {arquivo}")
    print("Azul: paradas | Vermelho: ônibus")


def main():
    if not TOKEN:
        print(
            "Token não encontrado. Configure SPTRANS_TOKEN "
            "no arquivo .env."
        )
        sys.exit(1)

    try:
        api = SPTransAPI(TOKEN)
        linha, paradas, veiculos = escolher_linha(api)
        criar_mapa(linha, paradas, veiculos)

    except (requests.RequestException, RuntimeError) as erro:
        print(f"\nNão foi possível concluir a atividade: {erro}")
        sys.exit(1)


if __name__ == "__main__":
    main()