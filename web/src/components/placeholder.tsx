import { CircleDashed } from "lucide-react";

export function SectionPlaceholder({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 py-24">
      <CircleDashed className="size-5 text-muted-foreground" />
      <h2 className="text-lg font-medium tracking-tight">{title}</h2>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  );
}
