import Head from 'next/head';
import { useState, useEffect } from 'react'; // <-- Added useEffect for CSR

// NOTE: We no longer import getAllResources
import * as dotenv from 'dotenv'; 
dotenv.config();

// This is the component that renders the home page
export default function Home() { // <-- Cleaned signature
  const [resources, setResources] = useState([]); // <-- Initialized as empty array
  const [formData, setFormData] = useState({ title: '', content: '', category: '' });
  const [message, setMessage] = useState('Loading resources...'); // <-- Initial loading message

  // Function to handle form input changes
  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  // NEW: Client-Side Fetching (CSR) Logic to load the resource list
  useEffect(() => {
    const fetchResources = async () => {
      // CRUCIAL FIX: Using the NEW full external IP: 41.144.78.121
      const API_URL = 'http://41.144.78.121:3000/api/resources'; 
      try {
        const res = await fetch(API_URL); 
        
        if (res.ok) {
          const data = await res.json();
          setResources(data);
          setMessage(''); // Clear loading message on success
        } else {
            setMessage('Error loading resources from API.');
        }
      } catch (error) {
          console.error("CSR Fetch Error:", error);
          setMessage('Network Error: Could not connect to API.');
      }
    };
    fetchResources();
  }, []); // Empty array ensures this runs only once

  // Function to handle form submission (API call)
  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage('Submitting...');
    
    // CRUCIAL FIX: Using the NEW full external IP for form submission: 41.144.78.121
    const API_URL = 'http://41.144.78.121:3000/api/resources'; 

    try {
      const res = await fetch(API_URL, { 
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (res.ok) {
        const newResource = await res.json();

        // Add the new resource to the state and clear form
        setResources([newResource, ...resources]);
        setFormData({ title: '', content: '', category: '' });
        setMessage('Resource created successfully!');

      } else {
        const errorData = await res.json();
        setMessage(`Submission Failed: ${errorData.message}`);
      }
    } catch (error) {
      console.error("Client-side error during POST:", error);
      setMessage(`An unexpected error occurred: ${error.message}`);
    }
  };

// --- Render Logic ---
  if (!Array.isArray(resources)) {
    return (
      <div className="container">
        <Head><title>Welcome SA - Resources</title></Head>
        <h1>Welcome SA Resources</h1>
        <p>Failed to load resources. Check server connection.</p>
      </div>
    );
  }

  return (
    <div className="container">
      <Head>
        <title>Welcome SA - Home</title>
      </Head>

      <main>
        <h1>🇿🇦 Welcome SA Resources Dashboard</h1>

        {/* Section 1: Create Resource Form */}
        <section style={{ border: '1px solid #ccc', padding: '15px', marginBottom: '20px' }}>
            <h2>Create New Resource (Admin Function)</h2>
            <form onSubmit={handleSubmit}>
                <div style={{ marginBottom: '10px' }}>
                    <label htmlFor="title">Title:</label>
                    <input
                        type="text"
                        name="title"
                        id="title"
                        value={formData.title}
                        onChange={handleChange}
                        required
                        style={{ width: '100%', padding: '8px' }}
                    />
                </div>
                <div style={{ marginBottom: '10px' }}>
                    <label htmlFor="category">Category:</label>
                    <input
                        type="text"
                        name="category"
                        id="category"
                        value={formData.category}
                        onChange={handleChange}
                        required
                        style={{ width: '100%', padding: '8px' }}
                    />
                </div>
                <div style={{ marginBottom: '10px' }}>
                    <label htmlFor="content">Content:</label>
            <textarea
                        name="content"
                        id="content"
                        value={formData.content}
                        onChange={handleChange}
                        required
                        rows="4"
                        style={{ width: '100%', padding: '8px' }}
                    ></textarea>
                </div>

                <button type="submit" style={{ padding: '10px 15px', background: '#0070f3', color: 'white', border: 'none', cursor: 'pointer' }}>
                    Submit Resource
                </button>
            </form>
            {/* Display message after submission */}
            {message && <p style={{ marginTop: '10px', color: message.includes('Success') ? 'green' : (message.includes('Error') || message.includes('Failed') ? 'red' : 'black') }}>{message}</p>}
        </section>


        {/* Section 2: Render the list of resources */}
        <section>
          <h2>Available Resources</h2>
          {resources.length === 0 && message.includes('Loading') ? (
            <p>{message}</p>
          ) : resources.length === 0 ? (
            <p>No resources found.</p>
          ) : (
            <ul style={{ listStyleType: 'none', padding: 0 }}>
              {resources.map((resource) => (
                <li key={resource._id} style={{ border: '1px solid #ddd', padding: '15px', marginBottom: '10px', borderRadius: '5px' }}>
                  <h3>{resource.title}</h3>
                  <p><strong>Category:</strong> {resource.category}</p>
                  <p>{resource.content}</p>
                  <small>Published: {new Date(resource.dateAdded).toLocaleDateString()}</small>
                </li>
              ))}
            </ul>
          )}
        </section>

      </main>

    </div>
  );
}
// NOTE: getServerSideProps has been deleted.
