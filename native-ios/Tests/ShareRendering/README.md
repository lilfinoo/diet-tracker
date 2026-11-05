# Compartilhamento: verificação do renderizador UIKit

Em um Mac Apple Silicon com Xcode instalado:

```sh
python3 native-ios/Tests/ShareRendering/verify.py --output /tmp/fittracker-share-images
```

O verificador compila cópias dos renderizadores e modelos atuais, sem substituir a lógica por uma implementação de teste. Usa UIKit via Mac Catalyst, sem abrir o app, sem simulador e sem acesso à API. O código temporário somente amplia a visibilidade dos símbolos privados para permitir a chamada pelo verificador.

São dez cenários: refeição com fundo branco, preto, foto real, macros ausentes e números grandes; treino com fundo branco, preto, sem foto, carga/repetições variáveis e prescrição sem séries registradas. Asserções verificam a presença da logo, resolução 1080 × 1920 e codificação/decodificação PNG. A inspeção de legibilidade e sobreposição é visual nos PNGs gerados; não há comparação automática de screenshots.

Isso não substitui testar a apresentação do compartilhamento em um iPhone e aplicativos de destino.
