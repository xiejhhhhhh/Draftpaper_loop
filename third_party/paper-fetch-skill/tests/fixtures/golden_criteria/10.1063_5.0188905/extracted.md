---
title: "Machine-learned atomic cluster expansion potentials for fast and quantum-accurate thermal simulations of wurtzite AlN"
authors: "Yang, Guang, Liu, Yuan-Bin, Yang, Lei, Cao, Bing-Yang"
doi: "10.1063/5.0188905"
source: "aip_html"
has_fulltext: true
content_kind: "fulltext"
has_abstract: true
token_estimate: 9240
---

# Machine-learned atomic cluster expansion potentials for fast and quantum-accurate thermal simulations of wurtzite AlN

## Abstract

Thermal transport in wurtzite aluminum nitride (*w-*AlN) significantly affects the performance and reliability of corresponding electronic devices, particularly when lattice strains inevitably impact the thermal properties of *w*-AlN in practical applications. To accurately model the thermal properties of *w-*AlN with high efficiency, we develop a machine learning interatomic potential based on the atomic cluster expansion (ACE) framework. The predictive power of the ACE potential against density functional theory (DFT) is demonstrated across a broad range of properties of *w*-AlN, including ground-state lattice parameters, specific heat capacity, coefficients of thermal expansion, bulk modulus, and harmonic phonon dispersions. Validation of lattice thermal conductivity is further carried out by comparing the ACE-predicted values to the DFT calculations and experiments, exhibiting the overall capability of our ACE potential in sufficiently describing anharmonic phonon interactions. As a practical application, we perform a lattice dynamics analysis using the potential to unravel the effects of biaxial strains on thermal conductivity and phonon properties of *w-*AlN, which is identified as a significant tuning factor for near-junction thermal design of *w-*AlN-based electronics.

## I. INTRODUCTION

Wurtzite aluminum nitride (*w-*AlN) emerges as a promising semiconductor, distinguished by various exceptional characteristics. These include an ultrawide bandgap<sup>1–3</sup> (∼6.1 eV), a large critical electric field<sup>1,3</sup> (∼15 MV/cm), a high sound velocity<sup>4</sup> (∼11 km/s), large piezoelectric coefficients,<sup>5</sup> a relatively high thermal conductivity<sup>6,7</sup> (⁠ $\kappa \sim 300{W/m} K$⁠), and a lattice similar to other semiconductors such as *w-*GaN. The large critical electric field stemming from the ultrawide bandgap results in Baliga's figure of merit (FOM) and Johnson's FOM of *w-*AlN significantly surpassing those of *w-*GaN or *β*-Ga<sub>2</sub>O<sub>3</sub>,<sup>1,3</sup> thereby establishing *w-*AlN as a remarkable candidate for novel high-power or radio frequency (RF) electronics.<sup>8,9</sup> Meanwhile, the ultrawide bandgap of *w-*AlN facilitates developments in deep-ultraviolet photonics.<sup>3,8,10,11</sup> The high sound velocity and piezoelectric performance render *w-*AlN suitable for fabricating microelectromechanical system (MEMS)-based resonators and filters, which are extensively applied in 5G communications.<sup>12–15</sup> In addition, the thermal conductivity of *w-*AlN is considered satisfactory; hence, *w-*AlN sometimes serves as high-*κ* substrates for high-power devices to improve the heat dissipation performance.<sup>9,16,17</sup> As depicted in Fig. 1, the bandgap and thermal conductivity of *w-*AlN are compared to other representative materials,<sup>2</sup> further exhibiting the significant promise of *w-*AlN.

![Figure](https://aipp.silverchair-cdn.com/aipp/content_public/journal/jap/135/8/10.1063_5.0188905/2/m_085105_1_5.0188905.figures.online.f1.jpeg?Expires=1782155914&Signature=aOHf8P-SD50tlqITjEP1nfqgwtyOu4HSWm-dDsvK9ofPY1nMsmWECK~PmLUNlCb6c~oHvlp-vOEE-U9K98SrK10-NtVJ5fodVLHjppbttAhLS5dV0ezchNMZ10nCH~BB~g3wNOskHoDrKDdiy3p20caM-YR~lciv9jiamGDy0J1LZUJFOpJv8UA8PqPF7BdLaFqwoH-RibSzsv4eXdlMehKWC4XhCtYDSg7YtwbKtgWyhn1I4SQT1emy-vN~NnyFzOmCLW8xj6yzc8zIn9mKeCdf8RVlezlT1R6SxfZsG9BUciNp1HC~l~dkgyUadoJQxBU9aqj-16plZwbW8W4ABQ__&Key-Pair-Id=APKAIE5G5CRDK6RD3PGA)

**Room temperature thermal conductivities of different materials vs their electronic bandgaps, including amorphous materials (e.g., a-Si, a-Ga2O3), polycrystals (poly-Si), metals (Cu), and nonmetallic crystals (e.g., w-AlN, w-GaN). For the data, refer to the literature.2,3,18–21 This plot reveals that w-AlN lies in the range of promising comprehensive performance (high thermal conductivity and ultrawide bandgap). Note that the average thermal conductivities are chosen for anisotropic materials (e.g., β-Ga2O3, r-TiO2). Refer to the image caption for details.**

Though the inherent characteristics of *w-*AlN are excellent, further studies on its properties remain necessary for developing next-generation electronics, especially in the aspects of (i) clarifying how the complex environment affects the physical properties, (ii) tuning the physical properties on demand, and (iii) analyzing the growth processes. One specific issue of interest pertains to the effects of lattice strains on the thermal properties of *w-*AlN. Since *w-*AlN is extensively used as the nucleation layer within the GaN high electron mobility transistors (HEMTs) to buffer lattice mismatch between *w-*GaN epilayers and substrates,<sup>22–25</sup> the residual stress within AlN is inevitable. However, the correlations between lattice strains with the thermal conductivity and phonon bands of *w-*AlN remain vague, which may affect the heat dissipation and reliability of corresponding devices.<sup>26,27</sup>

In addition to experimental approaches, atomistic simulations act as another avenue for gaining insights into the physical properties of novel materials,<sup>28</sup> which is traditionally represented by two techniques,<sup>29</sup> i.e., the first-principle calculations based on density functional theory (DFT) and the molecular dynamics (MD) simulations based on empirical potentials. Nevertheless, high computational cost limits the DFT methods for modeling transport properties, while the MD simulations based on simple empirical potentials are less accurate than DFT.<sup>30</sup> For *w-*AlN, several empirical potentials have been proposed, including the Stillinger–Weber (S–W),<sup>31</sup> Tersoff,<sup>32</sup> Vashishta,<sup>33</sup> and COMB3<sup>34</sup> models. However, each empirical potential generates divergent lattice parameters or phonon dispersions from those of DFT.<sup>33–35</sup> When predicting thermal conductivity, it is fundamental to accurately describe both harmonic and anharmonic interactions of phonons.<sup>36–38</sup> This places a heightened demand on the accuracy of interatomic potentials for *w-*AlN.

In recent years, machine learning (ML) interatomic potentials have attracted significant attention by effectively balancing computational efficiency with accuracy. A wealth of literature has shown that a well-built ML potential trained with the DFT reference data can provide an unbiased representation of potential energy surfaces and simultaneously exhibit strong transferability.<sup>36,39,40</sup> More importantly, the linear behavior in the computational cost of ML potentials enables them with much higher efficiency and scalability than DFT methods. Until now, several ML potential models have been proposed, such as the neural network potential (NNP),<sup>41,42</sup> Gaussian approximation potential (GAP),<sup>40,43,44</sup> spectral neighbor analysis potential (SNAP),<sup>45,46</sup> deep potential (DP),<sup>47,48</sup> moment tensor potential (MTP),<sup>49,50</sup> atomic cluster expansion (ACE) potential,<sup>51,52</sup> neural equivariant interatomic potential (NequIP),<sup>53</sup> Allegro,<sup>54</sup> and MACE.<sup>55,56</sup> The ACE potential is one of the most computationally efficient and quantum-accurate models available<sup>52</sup> and is also suitable for performing large-scale simulations on CPU platforms. Hence, ACE is chosen in this work.

Here, we introduce a machine-learned ACE potential<sup>51,52,57</sup> for *w-*AlN, aiming to facilitate the atomistic simulations of its thermal properties and gain insights into how tuning factors (such as lattice strains) influencing the phonon pictures. The remainder of this paper is organized as follows. In Sec. II, we concisely introduce the ACE methodology and the construction of the training database for *w-*AlN. In Sec. III, we comprehensively demonstrate the accuracy of our ACE potential in predicting various thermal and mechanical properties of *w-*AlN by comparison with either DFT calculations or experiments. Then, our ACE potential is applied to unravel the correlations between thermal conductivities and biaxial strains of *w-*AlN. Essential conclusions of this study are presented in Sec. IV.

## II. METHODS

### A. Atomic cluster expansion framework

In line with other common ML potentials, the ACE model also expresses the total energy of a given system as the sum of site energies,

**Equation 1.**

$$
\begin{matrix} {E = \sum\limits_{i}\varepsilon_{i},} \end{matrix}
$$

in which each $\varepsilon_{i}$ depends on its local atomic environment within a given cutoff radius $r_{cut}$⁠. Different from other many two-, three-, and many-body descriptors that are not strictly complete, the ACE framework provides an efficient representation of local atomic environments by means of a complete linear basis of body-ordered symmetric polynomials.51,52,57

Specifically, atomic energy contribution $\varepsilon_{i}$ in the ACE model is represented as

**Equation 2.**

$$
\begin{matrix} {\varepsilon_{i} = F({\varphi_{i}^{(1)},\ldots,\varphi_{i}^{(p)}}),} \end{matrix}
$$

where F is a generalized nonlinear function to be supplied and $\varphi_{i}^{(p)}$ is the fundamental building block of ACE, which is expanded by body-ordered functions within the set of neighbors for each atom i,

**Equation 3.**

$$
\begin{matrix} {\varphi_{i}^{(p)} = \sum\limits_{\mathbf{z}\mathbf{n}\mathbf{l}\mathbf{m}}{\overset{\sim}{\mathbf{c}}}_{z_{i}{\mathbf{z}\mathbf{n}\mathbf{l}\mathbf{m}}}^{(p)}\mathbf{A}_{i{\mathbf{z}\mathbf{n}\mathbf{l}\mathbf{m}}}.} \end{matrix}
$$

${\overset{\sim}{\mathbf{c}}}_{z_{i}{\mathbf{z}\mathbf{n}\mathbf{l}\mathbf{m}}}^{(p)}$ denotes expansion coefficients and vectors $\mathbf{z}$⁠, $\mathbf{n}$⁠, $\mathbf{l}$⁠, and $\mathbf{m}$ contain atomic species, indices for radial functions, and indices for spherical harmonics, respectively. The permutation-invariant many-body basis functions $\mathbf{A}_{i{\mathbf{z}\mathbf{n}\mathbf{l}\mathbf{m}}}$ are represented as

**Equation 4.**

$$
\begin{matrix} {\mathbf{A}_{i{\mathbf{z}\mathbf{n}\mathbf{l}\mathbf{m}}} = \prod\limits_{t = 1}^{v}A_{iz_{t}n_{t}l_{t}m_{t}},} \end{matrix}
$$

where the order of the product v determines the body order of a basis function. Meanwhile, the atomic base $A_{iz_{t}n_{t}l_{t}m_{t}}$ is given as

**Equation 5.**

$$
\begin{matrix} {A_{iz_{t}n_{t}l_{t}m_{t}} = \sum\limits_{j}\delta_{zz_{j}}\phi_{z_{i}z_{j}nlm}(\mathbf{r}_{ij}),} \end{matrix}
$$

in which $\mathbf{r}_{ij}$ is the relative position of neighbor atoms, and the one-particle basis $\phi_{z_{i}z_{j}nlm}$ consists of spherical harmonics functions $g_{nl}^{z_{i}z_{j}}$ and radial functions $Y_{lm}^{z_{i}z_{j}}$⁠,

**Equation 6.**

$$
\begin{matrix} {\phi_{z_{i}z_{j}nlm} = g_{nl}^{z_{i}z_{j}}Y_{lm}^{z_{i}z_{j}}.} \end{matrix}
$$

It is noteworthy that the expansion coefficients ${\overset{\sim}{\mathbf{c}}}_{z_{i}{\mathbf{z}\mathbf{n}\mathbf{l}\mathbf{m}}}^{(p)}$ in Eq. (3) cannot be directly used for model fitting because the many-body basis functions $\mathbf{A}$ do not satisfy rotational symmetries. By utilizing generalized Clebsch–Gordan coefficients to couple the elements of the basis function $\mathbf{A}$⁠, an invariant basis function $\mathbf{B}$ is obtained, $\mathbf{B} = {\mathbf{C}\mathbf{A}}$⁠. Consequently, a linear model invariant to translation, rotation, and permutation of like atoms can be written for the site energy of ACE,

**Equation 7.**

$$
\begin{matrix} {\varphi_{i} = \mathbf{c}^{T}B.} \end{matrix}
$$

The coefficients $\mathbf{c}$ are free model parameters that can be optimized during fitting. Further information about the ACE architecture can be found in the literature.<sup>51,52,57</sup> In this work, we employ the software package Pacemaker<sup>58</sup> for the parametrization of the ACE potential. The final ACE model associated with the detailed hyperparameters is freely available in the supplementary material.

### B. Construction of the training database

Structures in the training database are obtained from MD trajectories. Here, the empirical S-W potential<sup>31</sup> is adopted to carry out the MD simulations. This approach allows for sampling over extended time scales (∼ns) to ensure structural diversity, while it bypasses the computationally intensive *ab initio* MD and makes the sampling more efficient. In detail, the initial structure consists of a 3 × 3 × 3 supercell containing 108 atoms. The cell is then expanded or compressed with a scaling factor ranging from 0.95 to 1.05 on each lattice constant. Next, a series of MD simulations for each cell are performed with the canonical (NVT) ensemble at temperatures of 100, 500, and 1000 K. For each temperature, a 1-ns trajectory is produced, from which structures are sampled at uncorrelated intervals of 150 ps. Finally, a total of 13 608 local atomic environments are collected from all 21 MD trajectories.

All generated structures are subsequently subjected to single-point DFT calculations to obtain well-converged reference energies and forces for training. The DFT calculations are performed with the Vienna *ab initio* simulation package (VASP).<sup>59</sup> Exchange and correlation are treated by using the PBEsol functional<sup>60</sup> with a projector-augmented wave method.<sup>61</sup> Moreover, we adopt Gaussian smearing of 0.05 eV width to electronic levels, a 600-eV cutoff for plane wave expansions, and a maximum spacing of 0.2 Å<sup>−1</sup> for meshing the reciprocal space. The total energy is attained with a convergence criterion of less than 10<sup>−6</sup> eV in the self-consistent electronic iterations.

## III. RESULTS AND DISCUSSION

### A. Performance of the ACE potential for wurtzite AlN

The accuracy of our ACE potential is validated through a comparison with DFT-predicted energies and forces. The training and testing datasets comprise 36 612 and 4212 atomistic force components, respectively. In Fig. 2, we present a comparison of the total energies and atomic forces predicted by our potential with those derived from DFT. Notably, our ACE potential effectively reproduces the total energies, showcasing a remarkably low root-mean-squared error (RMSE) of 0.13 meV/atom for the testing datasets. Furthermore, the interatomic forces in the testing datasets are accurately predicted, with a relatively low RMSE of 5.01 meV/Å. The accuracy of both energy and force predictions achieved with our ACE potential is comparable to those of other reported works,<sup>40,43,52,62,63</sup> which demonstrates that our ACE potential serves as a robust representative of the DFT potential energy surface.

![Figure](https://aipp.silverchair-cdn.com/aipp/content_public/journal/jap/135/8/10.1063_5.0188905/2/m_085105_1_5.0188905.figures.online.f2.jpeg?Expires=1782155914&Signature=NTREgSB8FxUuQHwwxf6uMp2FZv75QO0uZgtZtkHQRw1VfdEYgO8oCMLJB4eilWVd6XLcJe4LMag~MB9oI7PVuALciyjpXQc-TnWM8Cyb3kI1P1XD05rYH6nC3GPXdaMorjJuath8Wz~Mq8a1puit2MhYV2ehUmQ9eJYZ2fk7kTcHPR9OFufsNzvhk7QZA0RpELHfTaIijy8KtY0FrqN04UkpNu2h6Wj5aKBSIeVm6Uw-Bs43m0W10augvB9Zq7pP1ot9PMFRAspX~d4BPx0lEHYuqntm9IGHFCF430sRj58e-5vsB9ChoAQ8Qh1SyJKBlMENt0UfLMPAC5gCAB5xuw__&Key-Pair-Id=APKAIE5G5CRDK6RD3PGA)

**Comparison of DFT-computed and ACE-predicted (a) total energies and (b) interatomic forces for w-AlN. Here, “Error” represents the absolute error. Refer to the image caption for details.**

Then, we assess the capability of our ACE potential to model the physical properties of *w*-AlN. Our evaluation begins by employing the ACE to predict lattice parameters, a fundamental property that significantly influences various intrinsic characteristics of a material. The lattice parameters produced by our ACE potential are as follows: $a = b = 3.115 58\text{Å}$⁠, $c = 4.985 13\text{Å}$⁠, and $\gamma = 120^{{^\circ}}$⁠. These values are in excellent agreement with both our DFT calculations and experimental results<sup>64</sup> (Table I). For comparison, lattice parameters are also predicted using the S-W potential<sup>31</sup> here as well as using the Tersoff potential elsewhere.<sup>35</sup> However, it is noteworthy that the relative errors in these predictions are considerably larger than those obtained with ACE.

**Table** Comparison of the lattice parameters of *w-*AlN determined by different methods.

| Method                               | Lattice parameter / ${a/b}(\text{Å})$ | Lattice parameter / $c(\text{Å})$ | Lattice parameter / *γ* (deg) | Max relative error against Expt. (%) |
| ------------------------------------ | ------------------------------------- | --------------------------------- | ----------------------------- | ------------------------------------ |
| ACE potential relaxation             | 3.115 58                              | 4.981 53                          | 120                           | 0.116                                |
| SW potential<sup>31</sup> relaxation | 3.080 02 | 5.029 65 | 120 | 1.027 |
| DFT relaxation (PBEsol)              | 3.112 88                              | 4.982 47                          | 120                           | 0.032                                |
| Experiment<sup>64</sup> | 3.111 97 | 4.980 89 | 120 | 0 |

The ACE potential is subsequently employed to predict the volumetric specific heat capacity (⁠ $C_{V}$⁠), coefficients of thermal expansion, and the bulk modulus of *w*-AlN. $C_{V}$ is calculated using the Phonopy package<sup>65–67</sup>. Figure 3(a) summarizes the $C_{V}$ obtained from our ACE potential, the DFT calculations, and the experimental measurements.<sup>68</sup> Obviously, the data generated by our ACE potential exhibit strong agreement with both DFT and experiments.

![Figure](https://aipp.silverchair-cdn.com/aipp/content_public/journal/jap/135/8/10.1063_5.0188905/2/m_085105_1_5.0188905.figures.online.f3.jpeg?Expires=1782155914&Signature=x4Ru-Q6nMBsB~4rkT-URu5e2RwOAScZIIhgF0E6-0JRUNm1ClQDEGf70tR8n1-gT5mduQz01Y4PXSN0TRm7hy2Hm0d4baOqV7w-dhTPwRGoscxyXCche7JbZ1vNf6E7n7cP6CV5tFuw76jylp9XaCoeLjMWMEgK78S6Sgy7GXFUomB1JrwRqMMAucCvYonGpns1lce2G0HCNbsv9OWTXqg6j1rK2ZtNtAGYT6oM6FvaHTo-cm7xvPReHb75WD7iqPenp35QDMM~xfj4hTcJ-QATkLuk2RC8oE18PDXlDCo1fnC2L8N3C77savmLmXXpW3nCZL-5XucVeFRt8GTTH9w__&Key-Pair-Id=APKAIE5G5CRDK6RD3PGA)

**Temperature-dependent (a) specific heat capacity, (b) thermal expansion coefficients, and (c) bulk modulus of w-AlN. (d) Phonon dispersion and phonon density of states (DOS) of w-AlN at 0 K predicted by DFT and the ACE potential. Refer to the image caption for details.**

Thermal expansion of w-AlN holds significant importance in practical applications, particularly when w-AlN is utilized as transition layers in III-V electronics, such as GaN HEMTs.22,23,25 This property determines heteroepitaxial strains arising from the thermal mismatches during growth processes.22 The coefficient of thermal expansion (CTE, denoted by $\alpha_{E}$⁠) is defined as

**Equation 8.**

$$
\begin{matrix} {\alpha_{E} = {\frac{1}{V_{T}}{\frac{\partial V_{T}}{\partial T},}}} \end{matrix}
$$

where V denotes the volume of the AlN unit cell and T represents the temperature. The CTEs are calculated under the quasi-harmonic approximation65 (QHA) implemented with Phonopy. As shown in Fig. 3(b), the ACE potential quantitatively reproduces the thermal expansion determined by DFT calculations. Both ACE and DFT predict that the CTEs are strongly dependent on temperatures between 0 and 1000 K. It is evident that as the temperature increases, the CTEs exhibit rapid growth up to ∼300 K, after which the slopes decrease at higher temperatures.

Moreover, a mechanical property, namely, the bulk modulus (⁠ $B_{T}$⁠) of *w-*AlN, is also determined by the ACE potential. As shown in Fig. 3(c), the ACE potential quantitatively reproduces the $B_{T}$ as DFT calculations. Both ACE and DFT predict a subtle decrease in the modulus as the temperature increases from 0 to 1000 K. In summary, it is obvious that our ACE potential is capable of accurately describing both thermal and mechanical properties.

The prediction of the phonon dispersions of a material is another crucial metric for the quality of a potential to describe lattice dynamics. We first calculate the second-order harmonic and third-order anharmonic interatomic force constants (IFCs) through the finite displacement method.<sup>69</sup> By combining the Phonopy package with the second-order IFCs calculated from our ACE and DFT, the phonon dispersions of *w-*AlN at 0 K are determined, as illustrated in Fig. 3(d). As a characteristic of the ionic crystal, the splitting of LO–TO phonons at the Γ-point is observed, which is attributed to the long-range Coulomb interactions.<sup>36</sup> Since our ACE model does not encompass the Coulomb interactions, we have incorporated the non-analytical correction<sup>26</sup> into the dynamical matrix to resolve the splitting of LO–TO phonons at the Γ point. Our results show that the ACE model accurately predicts the phonon frequencies at almost of all high-symmetry points and accurately captures the dispersion behavior of each phonon branch. Meanwhile, the phonon density of states (DOSs) calculated by ACE is almost identical to the DFT results.

In fact, although the absence of Coulomb terms introduces some errors in force calculations, it will be shown later that the accuracy of our potential remains sufficiently high to yield thermal conductivity predictions. If the long-range Coulomb interactions become crucial for other calculations, we will properly incorporate the Coulomb interactions with fixed partial charges before fitting the ACE model. This adjustment will automatically resolve the LO–TO splitting issue and improve the accuracy of force calculations.<sup>36</sup> Similar treatments for GaN can be found in the literature.<sup>43</sup>

### B. Thermal conductivity of wurtzite AlN

Herein, we utilize the second- and third-order IFCs to predict the thermal conductivity (⁠ $\kappa$⁠) of *w-*AlN. The Wigner transport equation (WTE)<sup>70–72</sup> is solved by the direct solution in Phono3py<sup>66,73,74</sup> package, with a 25 × 25 × 25 mesh for sampling the first Brillouin zone over temperatures within 100–600 K. Due to its wurtzite lattice, it is expected that the thermal conductivities of *w-*AlN exhibit approximate isotropy along both in-plane and cross-plane directions.<sup>27</sup>

We also conduct ShengBTE<sup>75</sup> calculations including the four-phonon processes (4ph)<sup>76</sup> for comparison with the WTE. Since the computational cost is extremely huge with 4ph involved, we resort to the sampling-accelerated method<sup>77</sup> with the settings “num_sample_process_4ph = 1E5” and “num_sample_process_4ph_phase_space = 1E5.” Meanwhile, a 16 × 16 × 16 mesh of the first Brillouin zone is set, and the value of “scalebroad” is taken as 0.1. The cutoff distances of the third- and fourth-order IFCs are selected to be the seventh nearest and the second nearest atom, respectively. These mentioned parameters are large enough to make it converge to the rigorous calculations,<sup>75–78</sup> though resulting in a negligible uncertainty due to random sampling.

As illustrated in Fig. 4(a), the ACE potential calculates the thermal conductivities of *w-*AlN along both in-plane and cross-plane directions. Though the physical pictures behind WTE and 4ph-scattering are different, their predictions are close indeed. The thermal conductivity predicted by ACE shows overall good agreements with our DFT calculations and experimental measurements (based on the three-sensor 2ω method proposed in our recent works).<sup>7,22,80</sup> Besides, the ACE-predicted values approximate the literature experiments<sup>2,79</sup> above room temperature as well, though the ACE overestimates thermal conductivities beneath 250 K owing to neglecting the phonon-defect scattering. Several theoretical and experimental studies<sup>27,79,81,82</sup> have discussed this issue, and researchers generally attribute the discrepancy between theoretical predictions and cryogenic experiments to the impacts of phonon-defect (e.g., point defects, dislocations, grain boundaries) scattering. Since the phonon-defect scattering rates are independent of temperature in principle,<sup>27</sup> they will dominate the phonon transport at low temperatures where the anharmonicity (normal and Umklapp processes) is weak.

![Figure](https://aipp.silverchair-cdn.com/aipp/content_public/journal/jap/135/8/10.1063_5.0188905/2/m_085105_1_5.0188905.figures.online.f4.jpeg?Expires=1782155914&Signature=wYkoLmSrO00AXyDeUevV1Q8fTYz8S7YvOdqBwCG4xPAFzXwxFM7G~IEITk7kLzPXJVd6bat-tLZDj4-YmSXZqb18TETFfi3B8doJz7D4WMZOupspkf1wiYwCp~B-aLjYlrmVoGGypOc-TompgbsXXVb1xh11646x0ZTayM4S5dr7QxNR5cH0PdUdEUvFrXfABjbJwWi~zN3YCEspOL1VT7OmA0eGjpZAQxpfl5gf59B0Jx4BRrSZvnroDiQdqQFj-mQBWiy8feWxKdoLFjfHETPAbrmRxLYX3OcMdGZflb2P~H~UIWhLoawEClhK2RCjsc650VRxpbQHMXv9tXxdpA__&Key-Pair-Id=APKAIE5G5CRDK6RD3PGA)

**(a) Comparison of w-AlN's thermal conductivities along the in-plane and cross-plane directions between the ACE model, DFT calculations, and experiments. Note that all the Phono3py calculations here have enabled the Wigner transport theory,70–72 while the ShengBTE calculations have included four-phonon effects.76 The literature experiments2,79 depicted here are all based on an isotropic assumption, while experiments based on our three-sensor 2ω method7 are capable of deriving the anisotropic thermal conductivity directly. (b) Comparison of accumulated thermal conductivity of w-AlN between the ACE model and DFT calculations, as a function of phonon frequency at 300 K along the in-plane and cross-plane directions, calculated by Phono3py. Refer to the image caption for details.**

The literature experiments depicted here are all based on an isotropic assumption, whereas our three-sensor 2ω method enables the direct derivation of thermal conductivities along different directions.<sup>7</sup> The brief introduction on the three-sensor 2ω method can be found in the supplementary material.

Furthermore, we conduct an equilibrium molecular dynamics (EMD) simulation based on the ACE potential to predict the *w-*AlN thermal conductivity. The large quantum effects at low temperatures significantly influence the MD-calculated thermal conductivity,<sup>28,81,83–86</sup> since the Debye temperature of *w-*AlN is quite high (⁠ $\Theta_{D}\ \sim \ 1000 K$⁠).<sup>87</sup> Hence, we only calculate the thermal conductivity at 1100 K, where the quantum effects could be reasonably neglected.<sup>84</sup> A bulk *w-*AlN system containing 4000 atoms is set as the initial configuration for EMD simulations conducted in the LAMMPS.<sup>88</sup> The length of each crystallographic direction reaching 10 unit cells achieves convergence for calculating the thermal conductivity of *w-*AlN.<sup>89,90</sup>

Periodic boundary conditions are applied to all three directions to mimic the infinite size of structures. A total of 4.5 ns EMD simulations based on the trained ACE potential are performed with a time step of 1 fs. After equilibrating the system in the isothermal–isobaric (NPT) ensemble for 500 ps, the system is switched to the microcanonical (NVE) ensemble for 4 ns to collect heat flux data. To mitigate the impacts of statistical uncertainties and errors, we conduct ten independent EMD simulations with different initial velocity distributions to obtain the averaged thermal conductivities at 1100 K. The thermal conductivity here is considered isotropic along the in-plane directions, so we average the thermal conductivity values along the *x*, *y* directions as the final in-plane thermal conductivity. The EMD results are $\kappa_{in}^{MD} = 51.0 \pm 5.8\ {W/m\ K}$ and $\kappa_{cr}^{MD} = 48.4 \pm 6.3\ {W/m\ K}$⁠, which are comparable to those of BTE calculations, as discussed in the supplementary material. On the AMD EPYC<sup>TM</sup> 7452 CPU platform, an average calculation efficiency of the ACE-based EMD simulations reaches 0.26 ms/MD-step/atom when calculating on a single thread (using GCC 9.1.0 compiler and LAMMPS 23-Jun-2022-Update3), which manifests the capability of the ACE potential for large-scale molecular dynamics.<sup>52</sup>

More detailed phonon transport characteristics of *w-*AlN are also calculated from the ACE potential by Phono3py. The accumulated thermal conductivity as a function of phonon frequency at 300 K is presented in Fig. 4(b), which further verifies the accuracy of the ACE potential compared to the DFT results. Obviously, the thermal conductivity is primarily contributed by acoustic phonon branches with frequencies below the “phonon bandgap,” whose contributions exceed 98.5% for both in- and cross-plane values. In addition, we also calculate the accumulated thermal conductivity as a function of phonon mean free path (MFP) based on the single-mode relaxation time approximation, as detailed in the supplementary material. The discussions on MFP imply that the size effect of *w*-AlN film's thermal conductivity is crucial for practical applications, which limits the heat dissipation performance of the corresponding electronic devices.<sup>22,23,25,91,92</sup>

### C. Influence of biaxial strain on thermal properties of wurtzite AlN

As discussed in Sec. I, there is an inevitable residual strain (stress) inside *w-*AlN in its practical applications, especially when *w-*AlN serves as the transition layer for a GaN HEMT by forming the GaN/AlN/Substrate heterojunction. Owing to the mismatches in lattice and thermal expansion between three materials, residual strain and lattice defects inside the *w-*AlN are general significant. Therefore, based on the trained ACE potential of *w-*AlN, we proceed to study the strain effects on lattice thermal conductivity of *w-*AlN.

In practical applications of transition layers, two kinds of strain exist within w-AlN, i.e., in-plane biaxial strain perpendicular to the polarization axis and cross-plane uniaxial strain along the polarization axis. Considering that in-plane stress is much more common than cross-plane stress in heterojunctions owing to the in-plane lattice mismatch26 and the uniaxial strain hardly affects thermal conductivity,93 we only investigate the biaxial strain effects in this work. Here, the strain is applied by modifying the lattice constants of the structure, and then the structure is relaxed with the in-plane lattice constant a (or $b$⁠) being settled. The biaxial strain is expressed by relative variation of the in-plane lattice constant,

**Equation 9.**

$$
\begin{matrix} {\sigma_{a} = {\frac{a - a_{0}}{a_{0}}.}} \end{matrix}
$$

Under in-plane biaxial strain states, the other lattice constant c will also vary to achieve minimal stress, and finally an optimized structure in the cross-plane direction is formed. Also, the changes of crystal symmetries are not detected under strain states in this work, i.e., AlN maintains a wurtzite structure with the space group P63/mmc. The introduction of lattice strains and the structure optimization are performed using the atomic simulation environment (ASE)94 package. Consequently, phonon properties as well as the thermal conductivity of w-AlN exhibit continuous changes under biaxial strain $\sigma_{a}$ states, ranging from −4% to 4%.

From a classical and intuitional perspective, compressive strain is expected to increase the thermal conductivity by augmenting the elasticity modulus and acoustic velocity.<sup>26</sup> The results, shown in Fig. 5, reveal that both in- and cross-plane thermal conductivity of *w-*AlN decrease remarkably under the +4% biaxial strain state (tensile) at room temperature, with the average thermal conductivity decreasing by 40%. Conversely, under the −4% biaxial strain state (compressive), the average thermal conductivity increases by 30%. In the temperature range of 200–400 K, lattice thermal conductivity decreases significantly; however, the decrease/increase trend depending on biaxial strain is nearly constant at different temperatures [Fig. 5(b)], implying that the influences of lattice strain and temperature on thermal conductivity should be independent. Meanwhile, the temperature dependence of thermal conductivity follows a similar trend under different biaxial strain states.

![Figure](https://aipp.silverchair-cdn.com/aipp/content_public/journal/jap/135/8/10.1063_5.0188905/2/m_085105_1_5.0188905.figures.online.f5.jpeg?Expires=1782155914&Signature=O7Lahg~99~Ek6h6tGXzVtCf3TQa9lePpm9j89VI0N8ytGYUfUtkO9kFuVeOe35fBxWX7Ry2LFqZNZDXdrpMMb~9qDPTtzmIdngiM01-SBchKWSEf~6Bd3ehlB~~1qLivrwDczgFlkGqqF3g6e1vquU7D~5WCFpqKL~TnHha8WBWwZ7csbCHD9LATQe7w~~EQoB~Rc8Nxz9iUuqiQXNC2MymdsNOfzcSqSDJqK~QQP1zjPB5lpDh8RX6D3EbBrILsKEnh09vqObiUG4NTYnklrMoBXEnxzbUUxsrdzolCO-lduWs-jiGWqbIcpzUVvvbI0Ook7bZSneAiM4mGIV9qkQ__&Key-Pair-Id=APKAIE5G5CRDK6RD3PGA)

**The effects of biaxial strains on thermal conductivities of w-AlN. (a) The dependence between thermal conductivities and the biaxial strains at 200−400 K, and (b) the variation of relative thermal conductivities at each temperature, i.e., the strained κ s t r a i n divided by the strain-less κ 0 at the same temperature. Refer to the image caption for details.**

Then, we investigate the changes of phonon properties under different strain states, to elucidate the correlation with their thermal conductivity. Based on the phonon BTE, lattice thermal conductivity can be expressed as26

**Equation 10.**

$$
\begin{matrix} {\kappa_{L}^{\alpha\beta} = \sum\limits_{\mathbf{q},\omega}C_{\mathbf{q},\omega}v_{\mathbf{q},\omega}^{\alpha}v_{\mathbf{q},\omega}^{\beta}\tau_{\mathbf{q},\omega},} \end{matrix}
$$

in which $\mathbf{q}$ and $\omega$ denote the phonon branch and the frequency of a specific phonon mode, respectively. Thus, lattice thermal conductivity primarily depends on the three variables, namely, volumetric specific heat $C_{\mathbf{q},\omega}$⁠, group velocity $v_{\mathbf{q},\omega}^{\alpha}$ (⁠ $v_{\mathbf{q},\omega}^{\beta}$⁠), and relaxation time $\tau_{\mathbf{q},\omega}$ of each phonon mode. Note that all these parameters are determined by the phonon dispersions, as illustrated in the supplementary material.

Figures 6(a) and 6(b) illustrate the phonon harmonic properties under different strain states, while Figs. 6(c) and 6(d) depict the anharmonic features. Volumetric specific heat of phonon modes reflects the energy level of a crystal system, varying with the phonon dispersions and volume of the unit cell correspondingly. As shown in Fig. 6(a), slight decreases of mode specific heat with tensile biaxial strains occur, implying a positive correlation to the change of thermal conductivity. In Fig. 6(b), phonon group velocity gradually increases from the tensile to compressive strain states, which is consistent with the increased thermal conductivity. Figure 6(c) shows that phonon relaxation time decreases under the tensile strain state and increases under the compressive strain state, which is consistent with the thermal conductivity variations as well. According to the results of phonon DOSs in the supplementary material, the phonon bandgaps are 0.65, 1.35, and 2.40 THz under tensile, free, and compressive strains, respectively. This determines the variations of relaxation time in principle, since a smaller (larger) phonon bandgap will enable more (less) available three-phonon scattering channels, thereby enhancing (suppressing) the three-phonon anharmonic scattering processes.<sup>26,95</sup>

![Figure](https://aipp.silverchair-cdn.com/aipp/content_public/journal/jap/135/8/10.1063_5.0188905/2/m_085105_1_5.0188905.figures.online.f6.jpeg?Expires=1782155914&Signature=ftONJsaEO63AVQ61Gojo3nRpm2cxQFCeLWT2CEOl8oNT1-HfrM9ZRumVImjwWERj0-Jscsn5kqawoFT~KrccjT3a~KlFh4vPqc6LilG3cxiAum1JFLnxRF10IDvxDiUVfQ6e9S2iusBORdUKAURSDL883ie26yFFjx2V5p3J1hrVTliWeZdl2KrvITDX0ndEyqUpagcSoD0GcNbYOwonQx5zY32U7s7sFbyr4PEKifxXufk5FyjgJ6wtvN6HjYeHMM9qewWe7fZajJaNbAEqguCamy-gl1xGJlmRbPBujG8gaZo1tvrdjdONdZDyYd3HxKgWpye4CNdwN5dSHAe6Qg__&Key-Pair-Id=APKAIE5G5CRDK6RD3PGA)

**Phonon properties under different biaxial strain states. (a) Mode volumetric specific heat, (b) phonon group velocity, (c) phonon relaxation time, and (d) Grüneisen parameters. Refer to the image caption for details.**

The Grüneisen parameter, an indicator of lattice anharmonicity,<sup>26,27</sup> is further analyzed here to back up the influences of strains on anharmonic scattering processes [Fig. 6(d)]. Obvious increases (decreases) in the Grüneisen parameters of acoustic phonon branches are observed under the tensile (compressive) strain state, in line with the variations of phonon bandgaps. More discussions on how and why lattice strains affect the phonon anharmonicity can be found in the supplementary material. Consequently, the consistent variations in mode specific heat, group velocity, relaxation time, and anharmonicity lead to significant changes in the lattice thermal conductivity<sup>26</sup> of *w*-AlN under different strain states.

The highlighted impacts of lattice strains on phonon properties should be favorable for tuning the heat dissipation performance of corresponding *w*-AlN-based electronic devices. By carefully engineering the residual strains within heteroepitaxial structures via annealing<sup>96,97</sup> or selecting substrates with specific lattice structures,<sup>26,98</sup> it is viable to optimize the lattice thermal properties on demand, facilitating near-junction thermal optimization of semiconductor devices.<sup>91,99</sup>

## IV. CONCLUSIONS

We have developed an ACE potential based on machine learning for atomistic simulations of monocrystalline *w-*AlN. Our ACE potential exhibits remarkable accuracy in reproducing the DFT potential energy surface of *w-*AlN, achieving an energy RMSE of ∼0.13 meV/atom and a force RMSE of ∼5.01 meV/Å for both Al and N atoms. Subsequently, the predictive power of ACE is demonstrated across a variety of properties of *w*-AlN, including ground-state lattice parameters, specific heat capacity, coefficients of thermal expansion, bulk modulus, phonon dispersions, and thermal conductivity. All these results show excellent agreement with the DFT calculations and experimental results, demonstrating that the ACE model sufficiently describes both harmonic and anharmonic phonon properties.

The lattice strain is proven as a significant tuning factor for thermal design of heteroepitaxial electronic devices. As a practical application of the ACE potential, we perform lattice dynamics simulations to unravel the effects of biaxial strains on thermal conductivity of *w-*AlN. The results indicate that a 4% biaxial tensile (compressive) strain approximately causes a 40% decrease (30% increase) in the thermal conductivity of *w-*AlN, while the influences of lattice strain and temperature on thermal conductivity appear to be independent. The investigations into phonon pictures under different strains reveal that the consistent variations in phonon mode heat capacity, group velocities, and relaxation times predominantly contribute to the variation of thermal conductivity, while all these factors stem from the variations in phonon band structures. Thus, it is feasible to facilitate near-junction thermal optimization of devices via strain engineering on phonon bands. The findings here are beneficial for the development of next-generation electronic devices.

## SUPPLEMENTARY MATERIAL

See the supplementary material for brief introductions to the experiments, additional discussions on phonon properties, and the ACE potential files developed for simulations in both LAMMPS and ASE calculators.

## ACKNOWLEDGMENTS

This work was financially supported by the National Natural Science Foundation of China (NNSFC) (Grant Nos. U20A20301, 52327809, 52250273, and 51825601).

## AUTHOR DECLARATIONS

### Conflict of Interest

The authors have no conflicts to disclose.

### Author Contributions

Guang Yang and Yuan-Bin Liu contributed equally to this work.

**Guang Yang:** Conceptualization (lead); Data curation (equal); Formal analysis (equal); Investigation (lead); Methodology (equal); Software (equal); Validation (lead); Visualization (lead); Writing – original draft (lead). **Yuan-Bin Liu:** Conceptualization (supporting); Data curation (equal); Formal analysis (equal); Investigation (supporting); Methodology (equal); Resources (supporting); Software (equal); Validation (supporting); Visualization (supporting); Writing – original draft (supporting); Writing – review & editing (supporting). **Lei Yang:** Methodology (supporting); Software (supporting). **Bing-Yang Cao:** Funding acquisition (lead); Project administration (lead); Resources (lead); Supervision (lead); Writing – review & editing (lead).

## DATA AVAILABILITY

The ACE potential is attached in the supplementary material, which can be used with the ML-PACE package on https://github.com/ICAMS/lammps-user-pace. The data that support the findings of this study are available from the corresponding author upon reasonable request.

## References (99 total, showing 99)

1. Doolittle W. A., Matthews C. M., Ahmad H., Motoki K., Lee S., Ghosh A., Marshall E. N., Tang A. L., Manocha P., Yoder P. D., Appl. Phys. Lett., 2023, 123, 070501
2. Xu R. L., Muñoz Rojo M., Islam S. M., Sood A., Vareskic B., Katre A., Mingo N., Goodson K. E., Xing H. G., Jena D., Pop E., J. Appl. Phys., 2019, 126, 185105
3. Yang J., Liu K., Chen X., Shen D., Prog. Quant. Electron., 2022, 83, 100397
4. Bickermann M., Kneissl M., Rass J., III-Nitride Ultraviolet Emitters Technology and Applications, 2016, 27-46
5. Tonisch K., Cimalla V., Foerster C., Romanus H., Ambacher O., Dontsov D., Sens. Actuators Phys., 2006, 132, 658-663
6. Rounds R., Sarkar B., Alden D., Guo Q., Klump A., Hartmann C., Nagashima T., Kirste R., Franke A., Bickermann M., Kumagai Y., Sitar Z., Collazo R., J. Appl. Phys., 2018, 123, 185107
7. Yang G., Cao B.-Y., Int. J. Heat Mass Transfer, 2024, 219, 124878
8. Bondokov R. T., Mueller S. G., Morgan K. E., Slack G. A., Schujman S., Wood M. C., Smart J. A., Schowalter L. J., J. Cryst. Growth, 2008, 310, 4020-4026
9. Yu R., Liu G., Wang G., Chen C., Xu M., Zhou H., Wang T., Yu J., Zhao G., Zhang L., J. Mater. Chem. C, 2021, 9, 1852-1873
10. Khan A., Balakrishnan K., Katona T., Nat. Photonics, 2008, 2, 77-84
11. Taniyasu Y., Kasu M., Diamond Relat. Mater., 2008, 17, 1273-1277
12. Zhu Y., Wang N., Sun C., Merugu S., Singh N., Gu Y., IEEE Electron Device Lett., 2016, 37, 1344-1346
13. Kaletta U. C., Santos P. V., Wolansky D., Scheit A., Fraschke M., Wipf C., Zaumseil P., Wenger C., Semicond. Sci. Technol., 2013, 28, 065013
14. Cassella C., Piazza G., IEEE Electron Device Lett., 2015, 36, 1192-1194
15. Yang K., Lin F., Wu Z., Fu D., Wu L., Zuo C., 2022, 106-109
16. Wang G., Zhou Y., IEEE Trans. Compon. Packag. Manuf. Technol., 2022, 12, 638-646
17. Tanaka A., Choi W., Chen R., Liu R., Mook W. M., Jungjohann K. L., Yu P. K. L., Dayeh S. A., J. Appl. Phys., 2018, 125, 082517
18. Liu Y.-B., Liang H.-L., Yang L., Yang G., Yang H.-A., Song S., Mei Z.-X., Csányi G., Cao B.-Y., Adv. Mater., 2023, 35, 2210873
19. Wong M. H., Bierwagen O., Kaplar R. J., Umezawa H., J. Mater. Res., 2021, 36, 4601-4615
20. Guo D.-Y., Li P.-G., Chen Z.-W., Wu Z.-P., Tang W.-H., Acta Phys. Sin., 2019, 68, 078501-1
21. Liang H., Han Z., Mei Z., Phys. Status Solidi A, 2021, 218, 2000339
22. Yang G., Cao B.-Y., J. Appl. Phys., 2023, 133, 045104
23. Liu Z.-K., Yang G., Cao B.-Y., Rev. Sci. Instrum., 2023, 94, 094902
24. Li H.-L., Shen Y., Hua Y.-C., Sobolev S. L., Cao B.-Y., J. Electron. Packag., 2022, 145, 011203
25. Cho J., Li Y., Hoke W. E., Altman D. H., Asheghi M., Goodson K. E., Phys. Rev. B, 2014, 89, 115301
26. Tang D.-S., Qin G.-Z., Hu M., Cao B.-Y., J. Appl. Phys., 2020, 127, 035102
27. Tang D.-S., Hua Y.-C., Zhou Y.-G., Cao B.-Y., Acta Phys. Sin., 2021, 70, 045101
28. Bao H., Chen J., Gu X.-K., Cao B.-Y., ES Energy Environ., 2018, 1, 16-55
29. Luo Y.-F., Li M.-K., Yuan H.-K., Liu H.-J., Fang Y., npj Comput. Mater., 2023, 9, 1-11
30. Babaei H., Guo R., Hashemi A., Lee S., Phys. Rev. Mater., 2019, 3, 074603
31. Zhou X. W., Jones R. E., Kimmer C. J., Duda J. C., Hopkins P. E., Phys. Rev. B, 2013, 87, 094303
32. Tungare M., Shi Y., Tripathi N., Suvarna P., (Shadi) Shahedipour-Sandvik F., Phys. Status Solidi A, 2011, 208, 1569-1572
33. Vashishta P., Kalia R. K., Nakano A., Rino J. P., J. Appl. Phys., 2011, 109, 033514
34. Choudhary K., Liang T., Mathew K., Revard B., Chernatynskiy A., Phillpot S. R., Hennig R. G., Sinnott S. B., Comput. Mater. Sci., 2016, 113, 80-87
35. Xiang H., Li H., Peng X., Comput. Mater. Sci., 2017, 140, 113-120
36. Liu Y.-B., Yang J.-Y., Xin G.-M., Liu L.-H., Csányi G., Cao B.-Y., J. Chem. Phys., 2020, 153, 144501
37. Barbalinardo G., Chen Z., Lundgren N. W., Donadio D., J. Appl. Phys., 2020, 128, 135104
38. Barbalinardo G., Chen Z., Dong H., Fan Z., Donadio D., Phys. Rev. Lett., 2021, 127, 025902
39. Gkeka P., Stoltz G., Barati Farimani A., Belkacemi Z., Ceriotti M., Chodera J. D., Dinner A. R., Ferguson A. L., Maillet J.-B., Minoux H., Peter C., Pietrucci F., Silveira A., Tkatchenko A., Trstanova Z., Wiewiora R., Lelièvre T., J. Chem. Theory Comput., 2020, 16, 4757-4775
40. Deringer V. L., Bartók A. P., Bernstein N., Wilkins D. M., Ceriotti M., Csányi G., Chem. Rev., 2021, 121, 10073-10141
41. Behler J., Parrinello M., Phys. Rev. Lett., 2007, 98, 146401
42. Behler J., Phys. Chem. Chem. Phys., 2011, 13, 17930-17955
43. Bartók A. P., Payne M. C., Kondor R., Csányi G., Phys. Rev. Lett., 2010, 104, 136403
44. Bartók A. P., Kondor R., Csányi G., Phys. Rev. B, 2013, 87, 184115
45. Thompson A. P., Swiler L. P., Trott C. R., Foiles S. M., Tucker G. J., J. Comput. Phys., 2015, 285, 316-330
46. Li X.-G., Hu C., Chen C., Deng Z., Luo J., Ong S. P., Phys. Rev. B, 2018, 98, 094104
47. Wang H., Zhang L., Han J., E W., Comput. Phys. Commun., 2018, 228, 178-184
48. Zeng J., Zhang D., Lu D., Mo P., Li Z., Chen Y., Rynik M., Huang L., Li Z., Shi S., Wang Y., Ye H., Tuo P., Yang J., Ding Y., Li Y., Tisi D., Zeng Q., Bao H., Xia Y., Huang J., Muraoka K., Wang Y., Chang J., Yuan F., Bore S. L., Cai C., Lin Y., Wang B., Xu J., Zhu J.-X., Luo C., Zhang Y., Goodall R. E. A., Liang W., Singh A. K., Yao S., Zhang J., Wentzcovitch R., Han J., Liu J., Jia W., York D. M., Car W. E. R., Zhang L., Wang H., J. Chem. Phys., 2023, 159, 054801
49. Shapeev A. V., Multiscale Model. Simul., 2016, 14, 1153-1173
50. Podryabinkin E. V., Shapeev A. V., Comput. Mater. Sci., 2017, 140, 171-180
51. Drautz R., Phys. Rev. B, 2019, 99, 014104
52. Lysogorskiy Y., van der Oord C., Bochkarev A., Menon S., Rinaldi M., Hammerschmidt T., Mrovec M., Thompson A., Csányi G., Ortner C., Drautz R., npj Comput. Mater., 2021, 7, 1-12
53. Batzner S., Musaelian A., Sun L., Geiger M., Mailoa J. P., Kornbluth M., Molinari N., Smidt T. E., Kozinsky B., Nat. Commun., 2022, 13, 2453
54. Musaelian A., Batzner S., Johansson A., Sun L., Owen C. J., Kornbluth M., Kozinsky B., Nat. Commun., 2023, 14, 579
55. Batatia I., Kovacs D. P., Simm G., Ortner C., Csanyi G., Adv. Neural Inf. Process. Syst., 2022, 35, 11423-11436
56. Kovács D. P., Batatia I., Arany E. S., Csányi G., J. Chem. Phys., 2023, 159, 044118
57. Witt W. C., van der Oord C., Gelžinytė E., Järvinen T., Ross A., Darby J. P., Ho C. H., Baldwin W. J., Sachs M., Kermode J., Bernstein N., Csányi G., Ortner C., J. Chem. Phys., 2023, 159, 164101
58. Bochkarev A., Lysogorskiy Y., Menon S., Qamar M., Mrovec M., Drautz R., Phys. Rev. Mater., 2022, 6, 013804
59. Kresse G., Furthmüller J., Phys. Rev. B, 1996, 54, 11169-11186
60. Perdew J. P., Ruzsinszky A., Csonka G. I., Vydrov O. A., Scuseria G. E., Constantin L. A., Zhou X., Burke K., Phys. Rev. Lett., 2008, 100, 136406
61. Blöchl P. E., Phys. Rev. B, 1994, 50, 17953-17979
62. Zuo Y., Chen C., Li X., Deng Z., Chen Y., Behler J., Csányi G., Shapeev A. V., Thompson A. P., Wood M. A., Ong S. P., J. Phys. Chem. A, 2020, 124, 731-745
63. Dusson G., Bachmayr M., Csányi G., Drautz R., Etter S., van der Oord C., Ortner C., J. Comput. Phys., 2022, 454, 110946
64. Paszkowicz W., Podsiadło S., Minikayev R., J. Alloys Compd., 2004, 382, 100-106
65. Togo A., Chaput L., Tanaka I., Hug G., Phys. Rev. B, 2010, 81, 174301
66. Togo A., J. Phys. Soc. Jpn., 2023, 92, 012001
67. Togo A., Chaput L., Tadano T., Tanaka I., J. Phys.: Condens. Matter, 2023, 35, 353001
68. Nipko J. C., Loong C.-K., Phys. Rev. B, 1998, 57, 10550-10554
69. Togo A., Tanaka I., Scr. Mater., 2015, 108, 1-5
70. Simoncelli M., Marzari N., Mauri F., Nat. Phys., 2019, 15, 809-813
71. Simoncelli M., Marzari N., Mauri F., Phys. Rev. X, 2022, 12, 041011
72. Di Lucente E., Simoncelli M., Marzari N., Phys. Rev. Res., 2023, 5, 033125
73. Togo A., Chaput L., Tanaka I., Phys. Rev. B, 2015, 91, 094306
74. Chaput L., Phys. Rev. Lett., 2013, 110, 265506
75. Li W., Carrete J., Katcho N. A., Mingo N., Comput. Phys. Commun., 2014, 185, 1747-1758
76. Han Z., Yang X., Li W., Feng T., Ruan X., Comput. Phys. Commun., 2022, 270, 108179
77. Guo Z., Han Z., Feng D., Lin G., Ruan X., 2023
78. Kundu A., Yang X., Ma J., Feng T., Carrete J., Ruan X., Madsen G. K. H., Li W., Phys. Rev.: Lett., 2021, 126, 115901
79. Cheng Z., Koh Y. R., Mamun A., Shi J., Bai T., Huynh K., Yates L., Liu Z., Li R., Lee E., Liao M. E., Wang Y., Yu H. M., Kushimoto M., Luo T., Goorsky M. S., Hopkins P. E., Amano H., Khan A., Graham S., Phys. Rev. Mater., 2020, 4, 044602
80. Hua Y.-C., Cao B.-Y., J. Appl. Phys., 2021, 129, 125107
81. Turney J. E., McGaughey A. J. H., Amon C. H., Phys. Rev. B, 2009, 79, 224305
82. Jiang P., Qian X., Li X., Yang R., Appl. Phys. Lett., 2018, 113, 232105
83. Turney J. E., Landry E. S., McGaughey A. J. H., Amon C. H., Phys. Rev. B, 2009, 79, 064301
84. Cao B.-Y., Yao W.-J., Ye Z.-Q., Carbon, 2016, 96, 711-719
85. Gu X., Fan Z., Bao H., J. Appl. Phys., 2021, 130, 210902
86. Xu Y.-X., Fan H.-Z., Zhou Y.-G., Rare Met., 2023, 42, 3914-3944
87. Wang J., Zhao M., Jin S. F., Li D. D., Yang J. W., Hu W. J., Wang W. J., Powder Diffr., 2014, 29, 352-355
88. Thompson A. P., Aktulga H. M., Berger R., Bolintineanu D. S., Brown W. M., Crozier P. S., in ‘t Veld P. J., Kohlmeyer A., Moore S. G., Nguyen T. D., Shan R., Stevens M. J., Tranchida J., Trott C., Plimpton S. J., Comput. Phys. Commun., 2022, 271, 108171
89. Huang Z., Wang Q., Liu X., Liu X., Phys. Chem. Chem. Phys., 2023, 25, 2349-2358
90. Sellan D. P., Landry E. S., Turney J. E., McGaughey A. J. H., Amon C. H., Phys. Rev. B, 2010, 81, 214305
91. Tang D.-S., Cao B.-Y., Int. J. Heat Mass Transfer, 2023, 200, 123497
92. Cho J., Li Z., Asheghi M., Goodson K. E., Annu. Rev. Heat Transfer, 2015, 18, 7-45
93. Seijas-Bellido J. A., Rurali R., Íñiguez J., Colombo L., Melis C., Phys. Rev. Mater., 2019, 3, 065401
94. Larsen A. H., Mortensen J. J., Blomqvist J., Castelli I. E., Christensen R., Dułak M., Friis J., Groves M. N., Hammer B., Hargus C., Hermes E. D., Jennings P. C., Jensen P. B., Kermode J., Kitchin J. R., Kolsbjerg E. L., Kubal J., Kaasbjerg K., Lysgaard S., Maronsson J. B., Maxson T., Olsen T., Pastewka L., Peterson A., Rostgaard C., Schiøtz J., Schütt O., Strange M., Thygesen K. S., Vegge T., Vilhelmsen L., Walter M., Zeng Z., Jacobsen K. W., J. Phys.: Condens. Matter, 2017, 29, 273002
95. Zheng Q., Li C., Rai A., Leach J. H., Broido D. A., Cahill D. G., Phys. Rev. Mater., 2019, 3, 014601
96. Mu F., Cheng Z., Shi J., Shin S., Xu B., Shiomi J., Graham S., Suga T., ACS Appl. Mater. Interfaces, 2019, 11, 33428-33434
97. Cheng Z., Mu F., You T., Xu W., Shi J., Liao M. E., Wang Y., Huynh K., Suga T., Goorsky M. S., Ou X., Graham S., ACS Appl. Mater. Interfaces, 2020, 12, 44943
98. Li X., Han B., Zhu R., Shi R., Wu M., Sun Y., Li Y., Liu B., Wang L., Zhang J., Tan C., Gao P., Bai X., Proc. Natl. Acad. Sci., 2023, 120, e2213650120
99. Hua Y.-C., Shen Y., Tang Z.-L., Tang D.-S., Ran X., Cao B.-Y., Adv. Heat Transfer, 2023, 56, 355-434
