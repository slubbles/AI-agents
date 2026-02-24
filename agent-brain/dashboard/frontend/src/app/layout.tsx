import type { Metadata } from "next";
import { Geist_Mono } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Agent Brain — Dashboard",
  description: "Autonomous self-improving research system",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${geistMono.variable} antialiased bg-[#050508] text-white`}>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 ml-0 lg:ml-64 p-4 sm:p-6 lg:p-8 overflow-y-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
