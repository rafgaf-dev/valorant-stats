/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PLAYER_ID?: string;
  readonly VITE_NEON_IMAGE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
