import { BrowserRouter, Routes, Route } from "react-router-dom";
import SPGSLandingPage from "./components/SPGSLandingPage";
import ParkingSelectionPage from "./components/ParkingSelectionPage";
import EngineeringFacultyLotPage from "./components/EngineeringFacultyLotPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SPGSLandingPage />} />
        <Route path="/select-lot" element={<ParkingSelectionPage />} />
        <Route
          path="/lot/engineering-faculty"
          element={<EngineeringFacultyLotPage />}
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;