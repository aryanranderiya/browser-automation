import Link from "next/link";

export default function Home() {
  return (
    <div className="grid grid-rows-[20px_1fr_20px] items-center justify-items-center min-h-screen p-8 pb-20 gap-16 sm:p-20 font-[family-name:var(--font-geist-sans)]">
      <main className="flex flex-col gap-[32px] row-start-2 items-center">
        <div className="flex flex-col items-center gap-4 text-center">
          <h1 className="text-4xl font-bold mb-2">
            CrustData Browser Automation
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-400 max-w-2xl">
            Control web browsers with natural language commands and automate
            data collection
          </p>
        </div>

        <div className="mt-8 flex flex-col gap-4 items-center">
          <div className="flex flex-wrap gap-4 justify-center">
            <Link
              href="/automation"
              className="rounded-full border border-solid border-transparent transition-colors flex items-center justify-center bg-foreground text-background gap-2 hover:bg-[#383838] dark:hover:bg-[#ccc] font-medium text-base h-12 px-8"
            >
              Automation Interface
            </Link>

            <Link
              href="/browser-agent"
              className="rounded-full border border-solid border-[#383838] dark:border-[#ccc] transition-colors flex items-center justify-center text-foreground gap-2 hover:bg-[#f0f0f0] dark:hover:bg-[#333] font-medium text-base h-12 px-8"
            >
              Browser Agent
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mt-8">
            <FeatureCard
              title="Browser Control"
              description="Control browsers remotely with simple natural language commands"
              icon="🌐"
            />
            <FeatureCard
              title="Persistent Sessions"
              description="Maintain browser state across multiple commands with interactive mode"
              icon="⚡"
            />
            <FeatureCard
              title="Data Extraction"
              description="Extract text, tables, links, and structured data from any website"
              icon="📊"
            />
            <FeatureCard
              title="AI-Powered Automation"
              description="Let the AI agent figure out how to complete complex browser tasks"
              icon="🤖"
            />
          </div>
        </div>
      </main>
      <footer className="row-start-3 flex gap-[24px] flex-wrap items-center justify-center">
        <p className="text-sm text-gray-500">
          CrustData Browser Automation &copy; {new Date().getFullYear()}
        </p>
      </footer>
    </div>
  );
}

function FeatureCard({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon: string;
}) {
  return (
    <div className="bg-white dark:bg-gray-900 p-6 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm hover:shadow-md transition-shadow">
      <div className="text-3xl mb-3">{icon}</div>
      <h3 className="text-xl font-semibold mb-2">{title}</h3>
      <p className="text-gray-600 dark:text-gray-400">{description}</p>
    </div>
  );
}
