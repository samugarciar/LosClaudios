import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,

  // El frontend nunca habla con Supabase ni con proveedores de modelo
  // directamente (README §10). Solo con su propio route handler /api/chat,
  // que a su vez decide entre el guion simulado y el backend real.
  // Si en el futuro se añade un origen externo, debe declararse aquí y
  // revisarse contra esa restricción.
};

export default nextConfig;
