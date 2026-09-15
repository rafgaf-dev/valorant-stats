/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_PLAYER_ID?: string;
  readonly VITE_NEON_IMAGE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}