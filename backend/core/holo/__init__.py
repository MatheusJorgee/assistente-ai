"""
Hologramas: dados REAIS e gratuitos para painéis visuais (mapa, viagem).

Fontes abertas, sem chave: Nominatim/OpenStreetMap (lugares), Overpass (pontos de interesse e
hospedagens mapeados), Wikivoyage/Wikipedia (guia), Open-Meteo (clima). NUNCA se inventa hotel,
endereço ou preço: onde não há dado real, o painel é omitido ou vira link de busca.

Módulos: schema (contrato do payload `holo_show`), http (cliente seguro com cache), geo, poi,
guia, clima, links, trip (cronograma por proximidade). A tool está em core/tools/holograma_tool.py.
"""
