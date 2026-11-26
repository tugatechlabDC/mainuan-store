# Changelog

Todas as alterações relevantes deste projeto são registadas neste ficheiro.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-PT/1.1.0/).

## [0.7.0] - 2026-11-26

### Adicionado
- 2 novas apps exclusivas Mainuan (total 10): **Mainuan Gerenciador Tarefas** (9.º) e **Mainuan Limpeza** (10.º).
- Banner "10 apps exclusivas Mainuan" (2.º banner, até 2027-08-30) com as 2 apps novas.
- Ícone da loja em 7 cores (azul por defeito, brow, claro, gray, green, red, rosa) que muda sozinho com a cor do sistema (KDE Plasma e GNOME). Pode forçar-se uma cor em `~/.config/mainuan-store/icon-color`.
- A própria Mainuan Store passa a atualizar-se pelas Atualizações da loja quando há uma nova release em github.com/mainuan/mainuan-store.
- Dependência nova: `libglib2.0-bin` (gdbus, para as notificações do sistema).

### Alterado
- A coluna "Ranking de Transferências" passa a **Recomendamos**.
- Ao abrir a loja, a cache é limpa e as atualizações são verificadas logo.
- No arranque do sistema, a verificação de atualizações é imediata (espera pela rede, se for preciso) e notifica na barra de notificações do sistema.
- Novo ícone azul (SVG + PNG 16/22/24/32/48; os PNG 64/128/256 foram removidos e o SVG escalável serve esses tamanhos).
- Versão das releases: a loja usa a tag (ex.: `v2.0`) como versão quando a tag é um número de versão.

### Corrigido
- A notificação de atualizações desaparece logo que as atualizações terminam.

## [0.6.3] - 2026-11-21

### Adicionado
- Banner temporário "8 apps exclusivas Mainuan" (`banners/00-apps-exclusivas-mainuan.jpg`), mostrado como 2.º banner, logo a seguir ao BEM-VINDO, de 2026-11-21 até 2027-08-30 (configurado em `banners/banners.json`).
- Pasta `/appimage` na raiz do disco, criada na instalação.

### Alterado
- As AppImages passam de `~/AppImages` para `/appimage`. As que já existiam são migradas automaticamente.
- `/appimage` fica protegida enquanto houver AppImages configuradas na loja: dono root e atributo imutável, sem permissões para o utilizador apagar ou alterar pastas ou ficheiros. Adicionar, atualizar e remover AppImages passa pelo helper (pkexec).
- Ao desinstalar a loja, a proteção é retirada e a pasta é devolvida ao utilizador.
- Novo ícone: azul da app (`#0399b2` → `#02829a`) e saco branco maior.
- Nova dependência: `e2fsprogs` (chattr).

### Corrigido
- Idioma pt-BR: sistemas em português do Brasil eram detetados como pt-PT. A deteção percorre agora todas as entradas de `LANGUAGE`, aceita `pt-BR`, e distingue a região quando só vem `pt`.


## 🎉 Lançamento inicial --> [0.6.2] - 2026-11-19

### Estado da versão
- Instalação, atualização e remoção de aplicações a partir de APT, Flathub (Flatpak), AppImage e ficheiros DEB locais.
- Início com banner de boas-vindas, banners rotativos, aplicações exclusivas Mainuan e Ranking de Transferências.
- Explorar com catálogo de 42 aplicações em 13 categorias e pesquisa em APT, Flatpak e AppImage.
- Atualizações de APT, Flatpak, AppImage e firmware (LVFS, com `fwupd`), com aviso na área de notificações.
- Gestão de AppImage: instalar por ficheiro ou arrastando para a janela, integração no menu e atualização por URL (GitHub, GitLab, Codeberg ou ligação direta).
- Definições: fonte padrão, repositórios APT e Flatpak, atualizações de firmware e avisos de atualizações.
- Menu lateral reduzido ou expandido, com a escolha guardada.
- Operações de administrador através de polkit (`pkexec`) com um programa auxiliar que só aceita comandos permitidos.
- Interface em português (PT), português (BR), inglês, francês e espanhol.

## Author

Desenvolvido e mantido por David Caixinha

## Contribute

Para reportar erros ou pedir funcionalidades:
- **Issues**: https://github.com/mainuan/mainuan-store/issues
- **Discussions**: https://github.com/mainuan/mainuan-store/discussions
- **Email**: info@mainuanlinux.com
