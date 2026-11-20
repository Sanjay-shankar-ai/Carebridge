import Link from "next/link";
import { FileQuestion, ArrowLeft, Home } from "lucide-react";
import { Button } from "../components/ui/Button";

export default function NotFound() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6 max-w-md mx-auto">
      <div className="w-16 h-16 rounded-full bg-[#E6F4F1] border border-[#CCFBF1] text-[#0F766E] flex items-center justify-center mb-4">
        <FileQuestion className="w-8 h-8" />
      </div>
      <span className="text-xs font-mono font-bold text-[#0F766E] uppercase tracking-wider mb-1">
        404 — Page Not Found
      </span>
      <h1 className="text-2xl font-semibold text-[#0F172A] tracking-tight mb-2">
        Clinical Pathway Page Not Found
      </h1>
      <p className="text-xs text-[#475569] leading-relaxed mb-6">
        The requested record or view does not exist or has been archived. You can return safely to your active role workspace.
      </p>

      <div className="flex items-center gap-3">
        <Link href="/">
          <Button variant="primary" leftIcon={<Home className="w-4 h-4" />}>
            Return to Dashboard
          </Button>
        </Link>
      </div>
    </div>
  );
}
