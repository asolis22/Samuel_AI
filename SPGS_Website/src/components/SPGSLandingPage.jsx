import { useNavigate } from "react-router-dom";

export default function SPGSLandingPage() {
  const navigate = useNavigate();

  const navItems = [
    { label: "About Us", href: "/about" },
    { label: "Meet the Team", href: "/team" },
    { label: "Future Implementation", href: "/future" },
    { label: "Gallery", href: "/gallery" },
  ];

  const clouds = [
    "top-28 left-20",
    "top-40 right-24",
    "bottom-28 left-28",
    "bottom-36 right-20",
    "top-64 left-1/2 -translate-x-1/2",
  ];

  const birds = [
    "top-36 right-40 rotate-6",
    "bottom-40 left-40 -rotate-6",
    "bottom-28 right-1/3 rotate-3",
  ];

  const balloons = [
    "top-24 left-1/4",
    "bottom-32 right-1/4",
  ];

  return (
    <div className="min-h-screen overflow-hidden bg-[#B7DDDA] text-[#6F4A2E]">
      <header className="relative z-20 border-b border-[#E6C4B7] bg-[#F2ECE1]/85 backdrop-blur-sm">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-6 lg:px-10">
          <div className="flex items-center gap-2">
            <img
              src="/adman-logo.png"
              alt="ADMAN Logo"
              className="h-16 w-auto object-contain"
            />
            <div className="flex flex-col justify-center leading-tight">
              <p className="text-base font-semibold tracking-[0.28em] text-[#2F4F4F]">
                ADMAN
              </p>
              <p className="text-sm tracking-[0.2em] text-[#2F4F4F]">
                Technologies
              </p>
            </div>
          </div>

          <nav className="hidden items-center gap-3 md:flex">
            {navItems.map((item) => (
              <button
                key={item.label}
                onClick={() => window.open(item.href, "_blank")}
                className="rounded-full border border-transparent px-4 py-2 text-sm font-semibold tracking-wide text-[#6F4A2E] transition hover:border-[#E6C4B7] hover:bg-[#FCDDD3]"
              >
                {item.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="relative flex min-h-[calc(100vh-80px)] items-center justify-center px-6 py-12">
        <div className="absolute inset-0">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(252,221,211,0.35),_transparent_35%)]" />

          {clouds.map((pos, i) => (
            <div
              key={i}
              className={`absolute ${pos} h-10 w-28 rounded-full bg-white/45 blur-[1px] before:absolute before:left-4 before:top-[-12px] before:h-12 before:w-12 before:rounded-full before:bg-white/45 after:absolute after:right-5 after:top-[-16px] after:h-14 after:w-14 after:rounded-full after:bg-white/45`}
            />
          ))}

          {birds.map((pos, i) => (
            <div key={i} className={`absolute ${pos} text-[#75B9BF]/75`}>
              <div className="relative h-16 w-24">
                <div className="absolute left-0 top-4 h-6 w-10 rounded-full bg-[#75B9BF]" />
                <div className="absolute left-6 top-7 h-1 w-10 bg-[#E6C4B7]" />
                <div className="absolute left-10 top-2 h-6 w-8 rounded-full bg-[#B7DDDA]" />
                <div className="absolute left-2 top-[-2px] h-8 w-8 origin-bottom rotate-[-30deg] rounded-full bg-[#75B9BF]/80" />
                <div className="absolute left-12 top-[-1px] h-8 w-8 origin-bottom rotate-[25deg] rounded-full bg-[#75B9BF]/65" />
                <div className="absolute right-0 top-7 h-1 w-4 bg-[#FCDDD3]" />
                <div className="absolute right-[-2px] top-6 h-0 w-0 border-b-[4px] border-l-[8px] border-t-[4px] border-b-transparent border-l-[#E6C4B7] border-t-transparent" />
              </div>
            </div>
          ))}

          {balloons.map((pos, i) => (
            <div key={i} className={`absolute ${pos}`}>
              <div className="relative flex flex-col items-center">
                <div className="grid h-24 w-16 grid-cols-2 overflow-hidden rounded-[50%] border-4 border-[#F2ECE1] bg-[#E6C4B7]">
                  <div className="bg-[#F2ECE1]" />
                  <div className="bg-[#FCDDD3]" />
                  <div className="bg-[#75B9BF]" />
                  <div className="bg-[#E6C4B7]" />
                </div>
                <div className="h-7 w-[2px] bg-[#6F4A2E]/60" />
                <div className="h-6 w-5 rounded-sm border border-[#F2ECE1] bg-white/70" />
              </div>
            </div>
          ))}
        </div>

        <section className="relative z-10 mx-auto flex w-full max-w-4xl flex-col items-center text-center">
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.55em] text-[#75B9BF] sm:text-base">
            Welcome To
          </p>

          <div className="mb-4 flex items-center gap-4 text-[#6F4A2E]/70">
            <div className="h-px w-12 bg-[#E6C4B7]" />
            <span className="text-sm tracking-[0.4em]">A</span>
            <div className="h-px w-12 bg-[#E6C4B7]" />
          </div>

          <h1 className="font-serif text-6xl leading-[0.95] text-[#6F4A2E] drop-shadow-sm sm:text-7xl md:text-8xl">
            S.P.G.S
          </h1>

          <p className="mt-6 text-xl font-medium tracking-[0.15em] text-[#6F4A2E] sm:text-2xl">
            Smart Parking Guidance System
          </p>

          <p className="mt-3 text-base tracking-[0.28em] text-[#2F4F4F] sm:text-lg">
            ADMAN Technologies
          </p>

          <button
            onClick={() => navigate("/select-lot")}
            className="mt-10 rounded-full border-2 border-[#E6C4B7] bg-[#FCDDD3] px-10 py-4 text-lg font-semibold tracking-[0.18em] text-[#6F4A2E] shadow-lg shadow-[#75B9BF]/15 transition hover:-translate-y-1 hover:bg-[#E6C4B7]"
          >
            Start
          </button>

          <div className="mt-16 grid w-full max-w-3xl grid-cols-1 gap-4 md:hidden">
            {navItems.map((item) => (
              <button
                key={item.label}
                onClick={() => window.open(item.href, "_blank")}
                className="rounded-2xl border border-[#E6C4B7] bg-[#F2ECE1]/80 px-5 py-4 text-sm font-semibold tracking-wide text-[#6F4A2E]"
              >
                {item.label}
              </button>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}