import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-[70vh] gap-6">
      <div className="text-6xl opacity-10">◈</div>
      <h1 className="text-4xl font-bold text-white/20">404</h1>
      <p className="text-white/30 text-sm">This route doesn&apos;t exist in the Agent Brain system.</p>
      <Link
        href="/"
        className="px-5 py-2.5 bg-[#00e5ff]/10 text-[#00e5ff] border border-[#00e5ff]/30 rounded-xl text-sm font-medium hover:bg-[#00e5ff]/20 transition-all"
      >
        ← Back to Overview
      </Link>
    </div>
  );
}
