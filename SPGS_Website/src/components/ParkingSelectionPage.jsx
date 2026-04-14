import { useNavigate } from "react-router-dom";

export default function ParkingSelectionPage() {
  const navigate = useNavigate();

  const parkingLots = [
    {
      name: "Engineering Faculty Lot",
      image: "/parking/eng-lot.png",
      path: "/lot/engineering-faculty",
    },
    {
      name: "Central Parking Lot",
      image: "/parking/central-lot.png",
      path: null,
    },
    {
      name: "Scheidt Family Performing Arts Center Lot",
      image: "/parking/scheidt-lot.png",
      path: null,
    },
    {
      name: "Zach H. Curlin Lot",
      image: "/parking/curlin-lot.png",
      path: null,
    },
    {
      name: "General Parking for Track",
      image: "/parking/track-lot.png",
      path: null,
    },
    {
      name: "Wellness Center Parking Lot",
      image: "/parking/wellness-lot.png",
      path: null,
    },
  ];

  return (
    <div className="min-h-screen bg-[#F2ECE1] text-[#6F4A2E]">
      <header className="border-b border-[#E6C4B7] bg-white/80 backdrop-blur-sm">
        <div className="mx-auto flex min-h-[88px] max-w-7xl items-center justify-center px-6 lg:px-10">
          <div className="flex items-center gap-3">
            <img
              src="/uofm-logo.jpg"
              alt="University of Memphis Logo"
              className="h-16 w-auto object-contain"
            />
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
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-14 lg:px-10">
        <section className="text-center">
          <p className="text-sm font-semibold uppercase tracking-[0.45em] text-[#003087]">
            University of Memphis
          </p>

          <h1 className="mt-5 font-serif text-5xl text-[#6F4A2E] sm:text-6xl md:text-7xl">
            S.P.G.S
          </h1>

          <p className="mt-5 text-2xl font-medium tracking-[0.12em] text-[#6F4A2E] sm:text-3xl">
            Smart Parking Guidance System
          </p>

          <p className="mx-auto mt-6 max-w-2xl text-lg text-[#2F4F4F] sm:text-xl">
            Please select the parking lot of your choice.
          </p>

          <p className="mt-4 text-base font-medium tracking-[0.08em] text-[#003087] sm:text-lg">
            Location: University of Memphis
          </p>
        </section>

        <section className="mt-14 grid grid-cols-1 gap-8 md:grid-cols-2 xl:grid-cols-3">
          {parkingLots.map((lot) => (
            <button
              key={lot.name}
              onClick={() => {
                if (lot.path) navigate(lot.path);
              }}
              className={`group overflow-hidden rounded-[1.75rem] border border-[#E6C4B7] bg-white text-left shadow-sm transition duration-300 ${
                lot.path
                  ? "hover:-translate-y-1 hover:shadow-lg"
                  : "cursor-not-allowed opacity-80"
              }`}
            >
              <div className="relative h-56 overflow-hidden bg-[#B7DDDA]">
                <img
                  src={lot.image}
                  alt={lot.name}
                  className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
                />
              </div>

              <div className="px-6 py-5">
                <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[#003087]">
                  University of Memphis
                </p>
                <h2 className="mt-2 text-xl font-semibold leading-snug text-[#6F4A2E]">
                  {lot.name}
                </h2>
              </div>
            </button>
          ))}
        </section>

        <div className="mt-12 flex justify-center">
          <button
            onClick={() => navigate("/")}
            className="rounded-full border-2 border-[#E6C4B7] bg-[#FCDDD3] px-8 py-3 text-base font-semibold tracking-[0.14em] text-[#6F4A2E] transition hover:bg-[#E6C4B7]"
          >
            Back
          </button>
        </div>
      </main>
    </div>
  );
}