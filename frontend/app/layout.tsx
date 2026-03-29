import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css" 

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// MELHORIA 1: Viewport e Theme Color (Essencial para o Mobile)
// Isso faz com que a barra de status do celular do navegador (Chrome/Safari) 
// fique da cor do sistema (slate-900) em vez de branca.
export const viewport: Viewport = {
  themeColor: "#0f172a", 
  width: "device-width",
  initialScale: 1,
  maximumScale: 1, // Previne que a tela dê "zoom" acidental ao focar no input pelo celular
};

export const metadata: Metadata = {
  title: "Quinta-Feira Core",
  description: "Interface Host do Assistente Modular Distribuído",
  icons: {
    icon: "/favicon.ico", 
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body
        // MELHORIA 2: Injeção de cores base diretamente no body
        // bg-slate-900 text-white evita o "Flash of White" (tela piscar branco) ao recarregar
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-slate-900 text-white overflow-hidden`}
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}