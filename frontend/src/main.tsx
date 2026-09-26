import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth } from "./auth";
import { Layout } from "./components/ui";
import Admin from "./pages/Admin";
import EditReview from "./pages/EditReview";
import Law from "./pages/Law";
import Laws from "./pages/Laws";
import Login from "./pages/Login";
import NewReview from "./pages/NewReview";
import ReviewResult from "./pages/ReviewResult";
import Reviews from "./pages/Reviews";
import "./theme.css";

const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<RequireAuth><Layout /></RequireAuth>}>
              <Route index element={<Reviews />} />
              <Route path="reviews/new" element={<NewReview />} />
              <Route path="reviews/:id" element={<ReviewResult />} />
              <Route path="reviews/:id/edit" element={<RequireAuth roles={["admin", "reviewer"]}><EditReview /></RequireAuth>} />
              <Route path="laws" element={<Laws />} />
              <Route path="laws/:docId" element={<Law />} />
              <Route path="admin" element={<RequireAuth roles={["admin"]}><Admin /></RequireAuth>} />
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
