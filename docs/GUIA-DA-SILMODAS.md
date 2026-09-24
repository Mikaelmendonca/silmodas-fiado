# Guia da Silmodas — para a dona da loja

Este guia é para **usar** o sistema no dia a dia. Nada aqui é difícil: se você sabe usar
WhatsApp, sabe usar a Silmodas.

## O que ela faz por você

Toda manhã, às 8h, o **celular avisa** quem está com o prazo acabando:

> **Vence hoje: Bruno**
> Prazo de Bruno finaliza hoje. Está devendo R$ 300,00.

Ela avisa **3 dias antes**, **1 dia antes**, **no dia** e, se passar do prazo, **todo dia** até
a pessoa pagar. Quem já pagou tudo nunca mais é avisado.

## Abrindo no celular

1. Abra o navegador do celular (Safari ou Chrome) e digite o endereço que o Mikael te passou.
   Parece com `http://192.168.0.15:8000`.
2. Digite a **senha** (o usuário pode deixar em branco ou colocar qualquer nome).
3. Para ficar como um aplicativo: toque em **Compartilhar → Adicionar à Tela de Início**.
   Vai aparecer o ícone rosa **S** entre seus apps.

> O celular precisa estar no **Wi-Fi da loja/casa** para abrir o painel. Os **avisos** chegam
> em qualquer lugar, com Wi-Fi ou internet do plano.

## Anotando uma venda a prazo

No fim da tela, em **Novo fiado**:

1. **Cliente:** o nome (ex.: Bruno).
2. **O que levou:** opcional (ex.: 2 camisetas).
3. **Valor:** quanto ele ficou devendo (ex.: `300,00`). Pode digitar `300`, `300,00` ou `300.50`.
4. **Prazo ou Vencimento:** preencha **um dos dois**, o outro se ajusta sozinho.
   - Prazo `30` → o vencimento vira daqui a 30 dias.
   - Ou escolha a data no calendário.
5. Toque em **Anotar fiado**. Pronto: a mensagem "Fiado anotado!" aparece.

Toque **uma vez só** no botão; ele fica apagado enquanto salva.

## Quando o cliente paga

Ache o nome na lista e toque em **Registrar pagamento**.

- Pagou tudo? Só confirme: o valor que aparece já é o que falta.
- Pagou uma parte? Troque pelo valor que ele pagou (ex.: `100`). O sistema guarda quanto
  **ainda falta**, e a barrinha rosa mostra quanto já foi pago.

## Cobrando

Em **Cobrar agora** ficam só os que **vencem hoje** ou **já passaram do prazo**. Se o cliente
tem telefone cadastrado, o botão **Cobrar no WhatsApp** abre uma mensagem educada já escrita.

## Perguntas rápidas

**Digitei um valor errado. E agora?** Toque em **Apagar** naquele fiado e anote de novo.

**Não chegou o aviso das 8h.** Toque em **Testar no celular** no painel. Se não chegar, o
celular precisa do aplicativo **ntfy** com o canal assinado (o Mikael configura uma vez).
Se o Mac estava desligado às 8h, o aviso chega assim que ele for ligado.

**O painel não abre no celular.** Confira se o celular está no mesmo Wi-Fi e se o Mac da loja
está ligado. Se ainda assim não abrir, chame o Mikael.

**Meus dados podem sumir?** Toda manhã o sistema guarda uma **cópia de segurança**
(pasta `backups`), com os últimos 30 dias.

---

# Para quem instala (Mikael)

No Mac da loja, uma vez:

```bash
git clone https://github.com/Mikaelmendonca/silmodas-fiado.git && cd silmodas-fiado
./scripts/instalar-mac.sh
```

O instalador prepara tudo, gera a **senha** e o **canal de avisos**, e mostra os endereços e
os 3 passos finais no celular. Depois disso a Silmodas liga sozinha sempre que o Mac iniciar.

- **Mac dormindo às 8h?** O aviso sai quando ele acordar. Para acordá-lo às 7h55 (opcional):
  `sudo pmset repeat wakeorpoweron MTWRFSU 07:55:00`
- **Ver o que está acontecendo:** `tail -f ~/Library/Logs/silmodas.log`
- **Restaurar um backup:** pare o serviço (`./scripts/desinstalar-mac.sh`), copie
  `backups/fiado-AAAA-MM-DD.db` por cima de `fiado.db` e rode o instalador de novo.
- **Atualizar o programa:** `git pull && ./scripts/instalar-mac.sh`
- **Desinstalar:** `./scripts/desinstalar-mac.sh` (os dados ficam guardados).
